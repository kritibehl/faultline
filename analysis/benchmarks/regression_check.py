from __future__ import annotations

import json
from pathlib import Path


def check_regression(current: dict, previous: dict | None = None) -> dict:
    if previous is None:
        return {
            "regression_detected": False,
            "reason": "no previous benchmark found",
            "duplicate_rate_status": "baseline_recorded",
        }

    current_faultline = max(current["faultline_duplicate_commit_rate_percent"])
    previous_faultline = max(previous["faultline_duplicate_commit_rate_percent"])

    if current_faultline > previous_faultline:
        return {
            "regression_detected": True,
            "reason": f"faultline duplicate rate increased from {previous_faultline}% to {current_faultline}%",
            "duplicate_rate_status": "regressed",
        }

    return {
        "regression_detected": False,
        "reason": "faultline duplicate rate did not increase",
        "duplicate_rate_status": "stable",
    }


def main() -> None:
    current_path = Path("benchmarks/results/benchmark_data.json")
    history_dir = Path("docs/benchmarks/history")
    history_dir.mkdir(parents=True, exist_ok=True)

    current = json.loads(current_path.read_text())
    previous_files = sorted(history_dir.glob("benchmark_*.json"))

    previous = json.loads(previous_files[-1].read_text()) if previous_files else None
    result = check_regression(current, previous)

    next_file = history_dir / f"benchmark_{len(previous_files) + 1:03d}.json"
    next_file.write_text(json.dumps(current, indent=2))
    Path("docs/benchmarks/regression_report.json").write_text(json.dumps(result, indent=2))

    print(json.dumps(result, indent=2))
    print(f"recorded {next_file}")


if __name__ == "__main__":
    main()
