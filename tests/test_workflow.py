"""
Unit tests for egressproof.workflow — uses pytest-httpserver to avoid real network calls.
"""

from __future__ import annotations

import pytest

from egressproof.workflow import WorkflowResult, execute_step, load_workflow, run_workflow


# ── load_workflow ─────────────────────────────────────────────────────────────

def test_load_workflow_valid(tmp_path):
    yaml_text = """
name: test-workflow
steps:
  - name: health
    method: GET
    path: /health
    expect_status: 200
"""
    f = tmp_path / "wf.yaml"
    f.write_text(yaml_text, encoding="utf-8")
    wf = load_workflow(str(f))
    assert wf["name"] == "test-workflow"
    assert len(wf["steps"]) == 1


def test_load_workflow_missing_file():
    with pytest.raises(FileNotFoundError):
        load_workflow("/nonexistent/path.yaml")


def test_load_workflow_no_steps(tmp_path):
    f = tmp_path / "wf.yaml"
    f.write_text("name: bad\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no 'steps' key"):
        load_workflow(str(f))


# ── execute_step ──────────────────────────────────────────────────────────────

def test_execute_step_get_pass(httpserver):
    httpserver.expect_request("/health").respond_with_data('{"status":"ok"}', status=200)
    step = {"name": "health", "method": "GET", "path": "/health", "expect_status": 200}
    result = execute_step(step, httpserver.url_for("").rstrip("/"))
    assert result.passed is True
    assert result.status_code == 200
    assert result.error is None


def test_execute_step_get_wrong_status(httpserver):
    httpserver.expect_request("/health").respond_with_data("error", status=500)
    step = {"name": "health", "method": "GET", "path": "/health", "expect_status": 200}
    result = execute_step(step, httpserver.url_for("").rstrip("/"))
    assert result.passed is False
    assert result.status_code == 500
    assert "500" in result.error


def test_execute_step_connection_error():
    """A step targeting a port with nothing listening should return FAIL gracefully."""
    step = {"name": "health", "method": "GET", "path": "/health", "expect_status": 200}
    result = execute_step(step, "http://localhost:19999", timeout=2.0)
    assert result.passed is False
    assert result.status_code is None
    assert result.error is not None


def test_execute_step_post_json(httpserver):
    httpserver.expect_request("/ask").respond_with_data('{"answer":"yes"}', status=200)
    step = {
        "name": "ask",
        "method": "POST",
        "path": "/ask",
        "json": {"question": "test?"},
        "expect_status": 200,
    }
    result = execute_step(step, httpserver.url_for("").rstrip("/"))
    assert result.passed is True


def test_execute_step_post_file(httpserver, tmp_path):
    httpserver.expect_request("/upload").respond_with_data('{"status":"stored"}', status=200)
    sample = tmp_path / "doc.txt"
    sample.write_text("hello world", encoding="utf-8")
    step = {
        "name": "upload",
        "method": "POST",
        "path": "/upload",
        "file": str(sample),
        "expect_status": 200,
    }
    result = execute_step(step, httpserver.url_for("").rstrip("/"))
    assert result.passed is True


# ── run_workflow ──────────────────────────────────────────────────────────────

def test_run_workflow_all_pass(httpserver, tmp_path):
    httpserver.expect_request("/health").respond_with_data('{"status":"ok"}', status=200)
    httpserver.expect_request("/ask").respond_with_data('{"answer":"ok"}', status=200)

    yaml_text = f"""
name: test-wf
base_url: "{httpserver.url_for('').rstrip('/')}"
steps:
  - name: health
    method: GET
    path: /health
    expect_status: 200
  - name: ask
    method: POST
    path: /ask
    json:
      question: hi
    expect_status: 200
"""
    f = tmp_path / "wf.yaml"
    f.write_text(yaml_text, encoding="utf-8")
    wf = load_workflow(str(f))
    result = run_workflow(wf, httpserver.url_for("").rstrip("/"))
    assert isinstance(result, WorkflowResult)
    assert result.passed is True
    assert all(s.passed for s in result.steps)


def test_run_workflow_partial_fail(httpserver, tmp_path):
    httpserver.expect_request("/health").respond_with_data("{}", status=200)
    httpserver.expect_request("/ask").respond_with_data("error", status=503)

    yaml_text = f"""
name: partial-fail
steps:
  - name: health
    method: GET
    path: /health
    expect_status: 200
  - name: ask
    method: POST
    path: /ask
    json:
      question: hi
    expect_status: 200
"""
    f = tmp_path / "wf.yaml"
    f.write_text(yaml_text, encoding="utf-8")
    wf = load_workflow(str(f))
    base = httpserver.url_for("").rstrip("/")
    result = run_workflow(wf, base)
    assert result.passed is False
    assert result.steps[0].passed is True
    assert result.steps[1].passed is False
    # All steps were attempted
    assert len(result.steps) == 2
