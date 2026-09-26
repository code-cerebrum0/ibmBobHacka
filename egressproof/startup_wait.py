"""Health-poll helper — waits for the application to become ready before running the workflow."""

import time

import requests


def wait_for_health(base_url: str, max_retries: int = 60, interval: float = 1.0) -> bool:
    """Poll GET {base_url}/health until the server responds or retries are exhausted.

    Returns True as soon as any HTTP response is received (any status code).
    Returns False if max_retries is exhausted without a response.
    """
    for attempt in range(1, max_retries + 1):
        print(f"  Waiting for app... (attempt {attempt}/{max_retries})")
        try:
            requests.get(f"{base_url}/health", timeout=interval)
            return True
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            time.sleep(interval)
    return False
