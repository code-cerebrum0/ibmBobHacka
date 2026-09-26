import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "requires_internet: test requires live internet access")
    config.addinivalue_line("markers", "requires_docker: test requires Docker daemon running")
