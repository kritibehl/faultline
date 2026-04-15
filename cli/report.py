from __future__ import annotations

import json
from pathlib import Path


RESULTS = Path("benchmarks/results/benchmark_data.json")


def main() -> None:
    if not RESULTS.exists():
        raise SystemExit("benchmark_data.json not found; run simulation first")

    data = json.loads(RESULTS.read_text())

    print("\nFaultline Benchmark Report")
    print("=" * 40)
    for rate, faultline_rate, naive_rate in zip(
        data["fault_rates_percent"],
        data["faultline_duplicate_commit_rate_percent"],
        data["naive_duplicate_commit_rate_percent"],
    ):
        print(
            f"Fault rate {rate}% | Faultline duplicate rate {faultline_rate}% | Naive duplicate rate {naive_rate}%"
        )


if __name__ == "__main__":
    main()
