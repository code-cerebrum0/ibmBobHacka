"""
Report writer for EgressProof.

Produces a human-readable text report and a machine-readable JSON report
from an EvidenceBundle.  Both are written to the output directory with a
timestamped filename.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from egressproof.evidence import EvidenceBundle


def _step_line(step) -> str:
    label = "PASS" if step.passed else "FAIL"
    suffix = f"  <- {step.error}" if step.error else ""
    return f"  {label:4}  {step.name}{suffix}"


def format_text_report(bundle: EvidenceBundle) -> str:
    """Return the human-readable report as a string."""
    lines: list[str] = []

    lines.append("=" * 60)
    lines.append("EGRESSPROOF REPORT")
    lines.append("=" * 60)
    lines.append(f"Application   : {bundle.app_name}")
    lines.append(f"Timestamp     : {bundle.timestamp}")
    lines.append(f"Network policy: {bundle.network_policy}")
    lines.append("")
    lines.append("Workflow:")
    lines.append(f"  {bundle.workflow_result.workflow_name}")
    lines.append("")
    lines.append("Step results:")
    for step in bundle.workflow_result.steps:
        lines.append(_step_line(step))
    lines.append("")

    if bundle.matched_patterns:
        lines.append("Failure evidence:")
        lines.append("")
        lines.append("  Suspicious patterns detected in container logs:")
        for p in bundle.matched_patterns:
            lines.append(f"    - {p}")
        lines.append("")
        if bundle.failed_steps:
            lines.append("  Failed workflow steps:")
            for s in bundle.failed_steps:
                lines.append(f"    - {s.name}: {s.error or 'unknown error'}")
        lines.append("")
        lines.append("  Probable reason:")
        lines.append(
            "    Embedding model was not packaged locally and attempted to"
            " download at runtime."
        )
    elif not bundle.passed:
        lines.append("Failure evidence:")
        lines.append("")
        lines.append("  No suspicious external-dependency patterns detected in logs.")
        lines.append("  Review raw container logs for further detail.")
        if bundle.failed_steps:
            lines.append("")
            lines.append("  Failed steps:")
            for s in bundle.failed_steps:
                lines.append(f"    - {s.name}: {s.error or 'unknown error'}")
    else:
        lines.append("External dependencies detected in logs : 0")

    lines.append("")
    verdict = "VERIFIED" if bundle.passed else "FAILED"
    lines.append(f"Result: {verdict}")
    lines.append("=" * 60)

    return "\n".join(lines)


def format_json_report(bundle: EvidenceBundle) -> dict:
    """Return the report as a JSON-serialisable dict."""
    return {
        "app_name": bundle.app_name,
        "timestamp": bundle.timestamp,
        "network_policy": bundle.network_policy,
        "workflow_name": bundle.workflow_result.workflow_name,
        "passed": bundle.passed,
        "steps": [
            {
                "name": s.name,
                "passed": s.passed,
                "status_code": s.status_code,
                "response_body": s.response_body,
                "error": s.error,
            }
            for s in bundle.workflow_result.steps
        ],
        "matched_patterns": bundle.matched_patterns,
        "container_logs": bundle.container_logs,
    }


def write_report(bundle: EvidenceBundle, output_dir: str = "reports") -> tuple[str, str]:
    """
    Write both .txt and .json reports to output_dir.

    Returns (txt_path, json_path).
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Build a filesystem-safe timestamp prefix
    ts = bundle.timestamp.replace(":", "-").replace("+", "").replace(".", "-")[:19]
    verdict = "pass" if bundle.passed else "fail"
    base = f"{ts}-{bundle.app_name.lower().replace(' ', '-')}-{verdict}"

    txt_path = os.path.join(output_dir, f"{base}.txt")
    json_path = os.path.join(output_dir, f"{base}.json")

    text = format_text_report(bundle)
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write(text)

    data = format_json_report(bundle)
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)

    return txt_path, json_path
