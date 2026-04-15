from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "benchmarks" / "results"


def run_cmd(env: dict[str, str], cmd: list[str]) -> None:
    result = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Faultline simulation entrypoint")
    parser.add_argument("--fault-rate", type=float, default=0.1, help="fault rate as decimal, e.g. 0.1 = 10%%")
    parser.add_argument("--jobs", type=int, default=200)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    fault_pct = int(args.fault_rate * 100)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["NAIVE_JOB_COUNT"] = str(args.jobs)
    env["NAIVE_WORKER_COUNT"] = str(args.workers)
    env["NAIVE_FAULT_PCT"] = str(fault_pct)
    env["FAULTLINE_FAULT_PCT"] = str(fault_pct)

    print(f"=== running naive harness at {fault_pct}% faults ===", flush=True)
    run_cmd(env, [sys.executable, "benchmarks/naive_queue_harness.py"])

    print(f"=== running faultline harness at {fault_pct}% faults ===", flush=True)
    run_cmd(env, [sys.executable, "benchmarks/faultline_harness.py"])

    print("=== exporting comparison ===", flush=True)
    run_cmd(env, [sys.executable, "benchmarks/export_comparison.py"])

    data = json.loads((RESULTS_DIR / "benchmark_data.json").read_text())
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
