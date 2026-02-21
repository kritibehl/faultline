import os
import sys
from pathlib import Path

import pytest


# Ensure repo root is importable (so `services.worker.reconciler` works)
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; export DATABASE_URL to run DB-backed tests.")
    return url