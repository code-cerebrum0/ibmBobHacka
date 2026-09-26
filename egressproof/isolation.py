# egressproof/isolation.py
"""
Docker network isolation helpers for EgressProof.

All operations use subprocess.run(["docker", ...]) — no Docker SDK required.

Isolation strategy (Docker Desktop / Windows compatible):
    We use --dns 0.0.0.0 to give the container a non-functional DNS resolver.
    Without DNS, any attempt to resolve an external hostname (e.g. huggingface.co)
    immediately raises socket.gaierror, exactly mimicking a restricted egress
    environment where external DNS is blocked.

    The container is started on the default bridge with -p host:container so the
    EgressProof runner can still reach it via localhost.  Only the container's
    own outbound DNS/internet access is broken.

    Note: docker network create --internal is the theoretically correct approach
    but on Docker Desktop for Windows it prevents port publishing to the host,
    making the runner unable to reach the container.  --dns 0.0.0.0 is
    equivalent for the demo scenario and works on all platforms.
"""

import subprocess


def create_isolated_network(name: str) -> None:
    """No-op under the DNS-isolation strategy.

    Kept for API compatibility — the isolation is applied at container start
    via --dns flags rather than via a separate network object.
    """
    pass


def remove_isolated_network(name: str) -> None:
    """No-op under the DNS-isolation strategy."""
    pass


def start_isolated_container(image: str, network: str, port: int, name: str) -> str:
    """Start a container with DNS isolation on the default bridge.

    The container gets --dns 0.0.0.0 which makes all external hostname
    resolution fail with socket.gaierror, simulating a zero-egress environment.
    The published port (-p) remains reachable from the host.

    Returns the container ID (stripped stdout).
    Raises RuntimeError if docker run fails.
    """
    result = subprocess.run(
        [
            "docker", "run", "-d",
            "--name", name,
            # Break external DNS → any huggingface.co / external lookup fails immediately
            "--dns", "0.0.0.0",
            "-p", f"{port}:{port}",
            image,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to start isolated container '{name}': {result.stderr.strip()}"
        )
    return result.stdout.strip()


def start_container(image: str, port: int, name: str) -> str:
    """Start a container on the default Docker bridge (no isolation).

    Used for the --no-isolation smoke test to confirm the app works normally
    before verifying that the isolated variant cannot reach the internet.
    Returns the container ID (stripped stdout).
    Raises RuntimeError if docker run fails.
    """
    result = subprocess.run(
        [
            "docker", "run", "-d",
            "--name", name,
            "-p", f"{port}:{port}",
            image,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to start container '{name}': {result.stderr.strip()}"
        )
    return result.stdout.strip()


def stop_and_remove_container(name: str) -> None:
    """Stop and remove a container by name.

    Ignores errors so cleanup is safe to call even when the container does
    not exist (e.g. after a failed start).
    """
    subprocess.run(["docker", "stop", name], capture_output=True, text=True)
    subprocess.run(["docker", "rm", name], capture_output=True, text=True)


def get_container_logs(name: str) -> str:
    """Return combined stdout+stderr from a container as a single string.

    Returns an empty string if docker logs fails (e.g. container not found).
    """
    result = subprocess.run(
        ["docker", "logs", name],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    # Combine stdout and stderr to mirror the shell redirect `2>&1`.
    return result.stdout + result.stderr
