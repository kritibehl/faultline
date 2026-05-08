from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    replay = json.loads(Path("replays/stale_worker_rejected.json").read_text())
    print("Replay:", replay["failure_case"])
    print("Expected:", replay["expected_behavior"])
    print("Observed:", replay["observed_result"])
    print("Metric:", replay["metric"])


if __name__ == "__main__":
    main()
