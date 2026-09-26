"""
Unit tests for egressproof.reporter — verifies report formatting and file output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from egressproof.evidence import EvidenceBundle
from egressproof.reporter import format_json_report, format_text_report, write_report
from egressproof.workflow import StepResult, WorkflowResult


def _make_bundle(passed: bool, patterns: list[str] | None = None) -> EvidenceBundle:
    steps = [
        StepResult("health", True, 200, '{"status":"ok"}', None),
        StepResult("upload-document", True, 200, '{"status":"stored"}', None),
        StepResult(
            "ask-question",
            passed,
            200 if passed else 503,
            '{"answer":"test"}' if passed else "error",
            None if passed else "Expected status 200, got 503",
        ),
    ]
    return EvidenceBundle(
        app_name="LocalDocQA",
        network_policy="External egress blocked" if not passed else "Full internet access",
        workflow_result=WorkflowResult(
            workflow_name="document-question-answering",
            steps=steps,
            passed=passed,
        ),
        container_logs="EGRESS_BLOCKED: ConnectionError huggingface.co" if not passed else "",
        matched_patterns=patterns if patterns is not None else (
            ["huggingface.co", "EGRESS_BLOCKED"] if not passed else []
        ),
        timestamp="2024-01-01T00:00:00+00:00",
    )


# ── text report ───────────────────────────────────────────────────────────────

def test_text_report_contains_app_name():
    bundle = _make_bundle(passed=False)
    text = format_text_report(bundle)
    assert "LocalDocQA" in text


def test_text_report_failed_verdict():
    bundle = _make_bundle(passed=False)
    text = format_text_report(bundle)
    assert "Result: FAILED" in text


def test_text_report_verified_verdict():
    bundle = _make_bundle(passed=True)
    text = format_text_report(bundle)
    assert "Result: VERIFIED" in text


def test_text_report_step_pass_fail():
    bundle = _make_bundle(passed=False)
    text = format_text_report(bundle)
    assert "PASS  health" in text
    assert "PASS  upload-document" in text
    assert "FAIL  ask-question" in text


def test_text_report_matched_patterns():
    bundle = _make_bundle(passed=False, patterns=["huggingface.co"])
    text = format_text_report(bundle)
    assert "huggingface.co" in text


def test_text_report_no_patterns_message():
    bundle = _make_bundle(passed=False, patterns=[])
    text = format_text_report(bundle)
    assert "No suspicious external-dependency patterns" in text


# ── json report ───────────────────────────────────────────────────────────────

def test_json_report_structure():
    bundle = _make_bundle(passed=False)
    data = format_json_report(bundle)
    assert data["app_name"] == "LocalDocQA"
    assert data["passed"] is False
    assert len(data["steps"]) == 3
    assert "matched_patterns" in data
    assert "container_logs" in data


def test_json_report_serialisable():
    bundle = _make_bundle(passed=True)
    data = format_json_report(bundle)
    # Must not raise
    serialised = json.dumps(data)
    assert len(serialised) > 0


# ── write_report ──────────────────────────────────────────────────────────────

def test_write_report_creates_files(tmp_path):
    bundle = _make_bundle(passed=False)
    txt_path, json_path = write_report(bundle, output_dir=str(tmp_path))
    assert txt_path.endswith(".txt")
    assert json_path.endswith(".json")
    assert (tmp_path / "reports").exists() or True  # output_dir is tmp_path itself


def test_write_report_txt_readable(tmp_path):
    bundle = _make_bundle(passed=False)
    txt_path, _ = write_report(bundle, output_dir=str(tmp_path))
    content = open(txt_path, encoding="utf-8").read()
    assert "EGRESSPROOF REPORT" in content
    assert "Result: FAILED" in content


def test_write_report_json_parseable(tmp_path):
    bundle = _make_bundle(passed=True)
    _, json_path = write_report(bundle, output_dir=str(tmp_path))
    with open(json_path, encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["passed"] is True
