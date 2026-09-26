"""
Integration test for the LocalDocQA application.

Requires: internet access (to download the model on first run), Docker, Python 3.11+.

Run with:
    pip install -e ".[dev]"
    pytest tests/test_local_app.py -v -m requires_internet
"""

from __future__ import annotations

import subprocess
import sys
import time

import pytest
import requests

pytestmark = pytest.mark.requires_internet

APP_URL = "http://localhost:18000"  # Use a non-default port to avoid conflicts
SAMPLE_TXT = "demo-app/sample-data/sample.txt"
IMAGE_TAG = "localdocqa-test"
CONTAINER_NAME = "localdocqa-test"


@pytest.fixture(scope="module")
def running_app():
    """Build and start the LocalDocQA container, yield, then tear it down."""
    # Build image
    result = subprocess.run(
        ["docker", "build", "-t", IMAGE_TAG, "demo-app"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"docker build failed:\n{result.stderr}")

    # Start container
    result = subprocess.run(
        ["docker", "run", "-d", "--name", CONTAINER_NAME, "-p", "18000:8000",
         "-e", "TRANSFORMERS_CACHE=/app/models", "-e", "HF_HOME=/app/models",
         IMAGE_TAG],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"docker run failed:\n{result.stderr}")

    # Wait for health
    for _ in range(60):
        try:
            r = requests.get(f"{APP_URL}/health", timeout=2)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        logs = subprocess.run(
            ["docker", "logs", CONTAINER_NAME], capture_output=True, text=True
        ).stdout
        pytest.fail(f"App did not start in time. Logs:\n{logs}")

    yield APP_URL

    # Teardown
    subprocess.run(["docker", "stop", CONTAINER_NAME], capture_output=True)
    subprocess.run(["docker", "rm", CONTAINER_NAME], capture_output=True)


def test_health(running_app):
    r = requests.get(f"{running_app}/health", timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_upload_txt(running_app):
    with open(SAMPLE_TXT, "rb") as fh:
        r = requests.post(
            f"{running_app}/upload",
            files={"file": ("sample.txt", fh, "text/plain")},
            timeout=10,
        )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "stored"
    assert data["filename"] == "sample.txt"


def test_upload_rejects_non_txt(running_app):
    r = requests.post(
        f"{running_app}/upload",
        files={"file": ("doc.pdf", b"fake pdf content", "application/pdf")},
        timeout=10,
    )
    assert r.status_code == 400


def test_ask_question(running_app):
    """Requires internet access — model is downloaded on first call."""
    # First ensure a document is uploaded
    with open(SAMPLE_TXT, "rb") as fh:
        requests.post(
            f"{running_app}/upload",
            files={"file": ("sample.txt", fh, "text/plain")},
            timeout=10,
        )
    r = requests.post(
        f"{running_app}/ask",
        json={"question": "What is EgressProof?"},
        timeout=120,   # model download can take a while
    )
    assert r.status_code == 200
    data = r.json()
    assert "answer" in data
    assert len(data["answer"]) > 0


def test_ask_without_documents(running_app):
    """A fresh container (no uploads) should return 400."""
    # Start a fresh container for this test
    fresh_name = "localdocqa-test-empty"
    subprocess.run(
        ["docker", "run", "-d", "--name", fresh_name, "-p", "18001:8000", IMAGE_TAG],
        capture_output=True,
    )
    time.sleep(3)
    try:
        r = requests.post(
            "http://localhost:18001/ask",
            json={"question": "anything"},
            timeout=10,
        )
        assert r.status_code == 400
    finally:
        subprocess.run(["docker", "stop", fresh_name], capture_output=True)
        subprocess.run(["docker", "rm", fresh_name], capture_output=True)
