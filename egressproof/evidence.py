"""
Evidence collection for EgressProof.

After a workflow run, this module fetches container logs and scans them for
patterns that indicate a blocked external dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from egressproof.isolation import get_container_logs
from egressproof.workflow import StepResult, WorkflowResult

# Patterns that indicate an attempted external connection in container logs.
SUSPICIOUS_PATTERNS: list[str] = [
    "huggingface.co",
    "hf.co",
    "EGRESS_BLOCKED",
    "ConnectionError",
    "socket.gaierror",
    "requests.exceptions.ConnectionError",
    "HTTPSConnectionPool",
    "No route to host",
    "Name or service not known",
    "Network is unreachable",
    "Temporary failure in name resolution",
    "OSError: [Errno",
]


@dataclass
class EvidenceBundle:
    """All evidence collected from a single EgressProof run."""

    app_name: str
    network_policy: str          # human-readable description, e.g. "External egress blocked"
    workflow_result: WorkflowResult
    container_logs: str          # raw combined stdout+stderr from docker logs
    matched_patterns: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def failed_steps(self) -> list[StepResult]:
        return [s for s in self.workflow_result.steps if not s.passed]

    @property
    def passed(self) -> bool:
        return self.workflow_result.passed


def collect_evidence(
    container_name: str,
    workflow_result: WorkflowResult,
    network_policy: str,
    app_name: str = "LocalDocQA",
) -> EvidenceBundle:
    """
    Fetch container logs and scan for suspicious patterns.

    Returns an EvidenceBundle regardless of whether suspicious patterns
    are found — honest reporting even if the hostname is not detectable.
    """
    logs = get_container_logs(container_name)

    matched: list[str] = []
    for pattern in SUSPICIOUS_PATTERNS:
        if pattern in logs:
            matched.append(pattern)

    return EvidenceBundle(
        app_name=app_name,
        network_policy=network_policy,
        workflow_result=workflow_result,
        container_logs=logs,
        matched_patterns=matched,
    )
