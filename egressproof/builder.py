"""
Docker image builder for EgressProof.
"""

from __future__ import annotations

import subprocess
import sys


def build_image(app_dir: str, tag: str) -> None:
    """
    Build a Docker image from the Dockerfile in app_dir.

    Streams build output to stdout in real-time.
    Raises RuntimeError if the build fails.
    """
    print(f"\n[egressproof] Building Docker image '{tag}' from '{app_dir}' ...")
    result = subprocess.run(
        ["docker", "build", "-t", tag, app_dir],
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Docker build failed for '{app_dir}' (exit {result.returncode})")
    print(f"[egressproof] Image '{tag}' built successfully.")
