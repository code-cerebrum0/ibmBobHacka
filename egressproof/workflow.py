"""Configuration-driven HTTP workflow runner for EgressProof."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import requests
import yaml

from egressproof.startup_wait import wait_for_health


@dataclass
class StepResult:
    name: str
    passed: bool
    status_code: int | None  # None if a network exception occurred
    response_body: str       # truncated to 500 chars
    error: str | None        # exception message, or None on success


@dataclass
class WorkflowResult:
    workflow_name: str
    steps: list[StepResult] = field(default_factory=list)
    passed: bool = False     # True only if ALL steps passed


def load_workflow(path: str) -> dict:
    """Load and validate a workflow YAML file.

    Raises FileNotFoundError if the path does not exist.
    Raises ValueError if the parsed dict has no "steps" key.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Workflow file not found: {path}")
    with p.open("r", encoding="utf-8") as fh:
        workflow = yaml.safe_load(fh)
    if "steps" not in workflow:
        raise ValueError(f"Workflow file '{path}' has no 'steps' key")
    return workflow


def execute_step(step: dict, base_url: str, timeout: float = 30.0) -> StepResult:
    """Execute a single workflow step and return its result."""
    name = step["name"]
    method = step["method"].upper()
    url = f"{base_url}{step['path']}"
    expect_status = step.get("expect_status")
    # Per-step timeout override takes precedence over the runner default.
    timeout = float(step.get("timeout", timeout))

    try:
        if method == "GET":
            response = requests.get(url, timeout=timeout)
        elif method == "POST":
            if "file" in step:
                file_path = Path(step["file"])
                with file_path.open("rb") as fh:
                    response = requests.post(
                        url,
                        files={"file": (file_path.name, fh, "text/plain")},
                        timeout=timeout,
                    )
            elif "json" in step:
                response = requests.post(url, json=step["json"], timeout=timeout)
            else:
                response = requests.post(url, timeout=timeout)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        status_code = response.status_code
        response_body = response.text[:500]
        passed = status_code == expect_status
        error = None if passed else f"Expected status {expect_status}, got {status_code}"

    except Exception as exc:  # noqa: BLE001
        status_code = None
        response_body = ""
        passed = False
        error = str(exc)

    label = "PASS" if passed else "FAIL"
    suffix = f" — {error}" if error else ""
    print(f"  [{label}] {name}{suffix}")

    return StepResult(
        name=name,
        passed=passed,
        status_code=status_code,
        response_body=response_body,
        error=error,
    )


def run_workflow(workflow: dict, base_url: str, timeout_per_step: float = 30.0) -> WorkflowResult:
    """Run all steps in a workflow, collecting results.

    Raises RuntimeError if the application does not become ready.
    All steps are always attempted regardless of individual failures.
    """
    if not wait_for_health(base_url):
        raise RuntimeError("Application did not become ready")

    name = workflow.get("name", "unnamed")
    print(f"\n=== Workflow: {name} ===")

    results: list[StepResult] = []
    for step in workflow["steps"]:
        result = execute_step(step, base_url, timeout=timeout_per_step)
        results.append(result)

    return WorkflowResult(
        workflow_name=name,
        steps=results,
        passed=all(r.passed for r in results),
    )
