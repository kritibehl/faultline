import os
import sys
from pathlib import Path

import pytest
import psycopg2


# Ensure repo root is importable so `services.*` works
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; export DATABASE_URL to run DB-backed tests.")

    # If DB isn't reachable, skip instead of failing the whole suite.
    try:
        conn = psycopg2.connect(url)
        conn.close()
    except Exception as e:
        pytest.skip(f"Postgres not reachable at DATABASE_URL: {e}")

    return url