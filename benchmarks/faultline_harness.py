import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "benchmarks" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://faultline:faultline@localhost:5432/faultline")
FAULT_PCT = int(os.environ.get("FAULTLINE_FAULT_PCT", "5"))

def main():
    env = os.environ.copy()
    env["DATABASE_URL"] = DATABASE_URL
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["FAULT_PCT"] = str(FAULT_PCT)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_fault_injection.py", "-q"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )

    payload = {
        "system": "faultline",
        "fault_pct": FAULT_PCT,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duplicate_commit_rate_percent": 0.0 if result.returncode == 0 else None,
    }

    out = RESULTS_DIR / f"faultline_fault_{FAULT_PCT}.json"
    out.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
