from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    history_dir = Path("docs/benchmarks/history")

    files = sorted(history_dir.glob("benchmark_*.json"))

    trend = []

    for idx, f in enumerate(files, 1):
        data = json.loads(f.read_text())

        trend.append({
            "run": idx,
            "max_duplicate_rate": max(
                data["faultline_duplicate_commit_rate_percent"]
            ),
        })

    Path("reports/incidents/benchmark_trends.json").write_text(
        json.dumps(trend, indent=2)
    )

    print(json.dumps(trend, indent=2))


if __name__ == "__main__":
    main()
