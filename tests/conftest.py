"""
tests/conftest.py
──────────────────
Shared pytest fixtures for Faultline integration tests.

All tests require a live PostgreSQL instance with the full schema applied.
Run `make migrate` before running the test suite.

    docker compose up -d
    make migrate
    pytest tests/
"""

import os
import pytest


@pytest.fixture(scope="session")
def database_url() -> str:
    """
    PostgreSQL connection string for integration tests.
    Reads from DATABASE_URL env var, falls back to the docker-compose default.
    """
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql://faultline:faultline@localhost:5432/faultline",
    )
    return url