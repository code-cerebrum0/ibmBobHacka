"""
Integration tests for Docker isolation — requires Docker to be installed and running.

These tests verify that `docker network create --internal` actually blocks outbound
internet from containers while the host can still reach them via published ports.

Run with:
    pytest tests/test_isolation.py -v -m requires_docker
"""

from __future__ import annotations

import subprocess
import time

import pytest
import requests

from egressproof.isolation import (
    create_isolated_network,
    get_container_logs,
    remove_isolated_network,
    start_container,
    start_isolated_container,
    stop_and_remove_container,
)

pytestmark = pytest.mark.requires_docker

NETWORK_NAME = "egressproof-test-isolated"
CONTAINER_NAME = "egressproof-test-container"


@pytest.fixture(autouse=True)
def cleanup():
    """Ensure test container and network are removed before and after each test."""
    stop_and_remove_container(CONTAINER_NAME)
    remove_isolated_network(NETWORK_NAME)
    yield
    stop_and_remove_container(CONTAINER_NAME)
    remove_isolated_network(NETWORK_NAME)


def test_create_isolated_network_idempotent():
    """Creating the same network twice should not raise."""
    create_isolated_network(NETWORK_NAME)
    create_isolated_network(NETWORK_NAME)  # second call must be idempotent
    remove_isolated_network(NETWORK_NAME)


def test_isolated_network_blocks_internet():
    """A container on the internal network should not be able to reach the internet."""
    create_isolated_network(NETWORK_NAME)

    result = subprocess.run(
        [
            "docker", "run", "--rm", "--network", NETWORK_NAME,
            "alpine", "ping", "-c", "1", "-W", "2", "8.8.8.8",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    # ping should fail (non-zero exit) when the network is isolated
    assert result.returncode != 0, (
        "Expected ping to 8.8.8.8 to fail on isolated network, but it succeeded. "
        f"stdout: {result.stdout}"
    )


def test_host_can_reach_container_via_published_port():
    """
    The host should be able to reach the container via its published port
    even when the container is on an isolated network.
    """
    create_isolated_network(NETWORK_NAME)

    # Use a simple nginx container as a stand-in — it responds on port 80
    result = subprocess.run(
        [
            "docker", "run", "-d", "--name", CONTAINER_NAME,
            "--network", NETWORK_NAME,
            "-p", "18080:80",
            "nginx:alpine",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"Could not start nginx container: {result.stderr}")

    # Wait for nginx to start
    for _ in range(20):
        try:
            r = requests.get("http://localhost:18080", timeout=1)
            if r.status_code == 200:
                break
        except Exception:
            time.sleep(0.5)
    else:
        pytest.fail("nginx did not start in time on the isolated network")


def test_get_container_logs_returns_string():
    """get_container_logs should return a string (possibly empty) without raising."""
    start_container("nginx:alpine", 18081, CONTAINER_NAME)
    time.sleep(1)
    logs = get_container_logs(CONTAINER_NAME)
    assert isinstance(logs, str)
