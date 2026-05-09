from __future__ import annotations

import json
from pathlib import Path


def compute_score(metrics: dict) -> dict:
    score = 100

    duplicate_rate = max(metrics.get("faultline_duplicate_commit_rate_percent", [0]))
    stale_rejections = metrics.get("stale_write_rejected_total", 0)
    invariant_violations = metrics.get("invariant_violations", 0)

    reasons = []

    if duplicate_rate > 0:
        score -= 50
        reasons.append("duplicate commits detected")

    if invariant_violations > 0:
        score -= 40
        reasons.append("invariant violations detected")

    if stale_rejections > 0:
        reasons.append("stale writes rejected successfully")

    if score >= 95:
        status = "excellent"
    elif score >= 80:
        status = "good"
    else:
        status = "unsafe"

    return {
        "correctness_score": score,
        "status": status,
        "reasons": reasons,
    }


def main() -> None:
    metrics = {
        "faultline_duplicate_commit_rate_percent": [0.0],
        "stale_write_rejected_total": 3,
        "invariant_violations": 0,
    }

    result = compute_score(metrics)

    Path("reports/incidents").mkdir(parents=True, exist_ok=True)

    Path("reports/incidents/correctness_score.json").write_text(
        json.dumps(result, indent=2)
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
