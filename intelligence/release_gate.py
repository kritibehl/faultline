from __future__ import annotations

import json
from pathlib import Path


def evaluate(metrics: dict) -> dict:
    duplicate_rate = max(metrics.get("faultline_duplicate_commit_rate_percent", [0]))
    coordination_overhead = metrics.get("coordination_overhead_percent", 0)

    if duplicate_rate > 0:
        return {
            "release_decision": "block",
            "reason": "duplicate commits detected",
            "safe_to_operate": False,
        }

    if coordination_overhead > 60:
        return {
            "release_decision": "review",
            "reason": "coordination overhead exceeds threshold",
            "safe_to_operate": True,
        }

    return {
        "release_decision": "ship",
        "reason": "correctness invariants preserved",
        "safe_to_operate": True,
    }


def main() -> None:
    metrics = {
        "faultline_duplicate_commit_rate_percent": [0.0],
        "coordination_overhead_percent": 46.5,
    }

    result = evaluate(metrics)

    Path("reports/incidents").mkdir(parents=True, exist_ok=True)

    Path("reports/incidents/release_gate.json").write_text(
        json.dumps(result, indent=2)
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
