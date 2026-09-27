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


def format_text_report(bundle: EvidenceBundle) -> str:
    """Return the human-readable report as a string."""
    lines: list[str] = []

    lines.append("")
    lines.append("EGRESSPROOF")
    lines.append("")
    lines.append(f"Application : {bundle.app_name}")
    lines.append(f"Boundary    : {bundle.network_policy}")
    lines.append("")

    for step in bundle.workflow_result.steps:
        mark = "✓" if step.passed else "✗"
        lines.append(f"  {mark} {step.name}")
    lines.append("")

    if bundle.matched_patterns:
        # Surface the most informative external hostnames (not internal noise tokens)
        _noise = {"EGRESS_BLOCKED", "ConnectionError", "socket.gaierror",
                  "requests.exceptions.ConnectionError", "HTTPSConnectionPool",
                  "No route to host", "Name or service not known",
                  "Network is unreachable", "Temporary failure in name resolution",
                  "OSError: [Errno"}
        external_hosts = [p for p in bundle.matched_patterns if p not in _noise]

        if external_hosts:
            lines.append("Unexpected runtime dependencies:")
            for host in external_hosts:
                lines.append(f"  {host}")
            lines.append("")

        if bundle.failed_steps:
            lines.append("Evidence:")
            lines.append(
                "  Runtime model download attempted while external"
                " name resolution was unavailable."
            )
            lines.append("")
    elif not bundle.passed:
        lines.append("Evidence:")
        lines.append("  Workflow failed. No external-dependency patterns detected in logs.")
        lines.append("  Review raw container logs for further detail.")
        lines.append("")
    else:
        lines.append("Unexpected runtime dependencies detected: 0")
        lines.append("")

    verdict = "VERIFIED" if bundle.passed else "FAILED"
    lines.append(f"RESULT: {verdict}")

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
