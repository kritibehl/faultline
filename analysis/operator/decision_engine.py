from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from analysis.operator.failure_classifier import classify_failure


def decide(metrics: dict) -> dict:
    signal = classify_failure(metrics)

    decision = {
        "safe_to_operate": signal.safe_to_operate,
        "failure_family": signal.failure_family,
        "severity": signal.severity,
        "reason": signal.reason,
        "recommended_action": signal.recommended_action,
    }

    if signal.severity in {"critical", "high"} and not signal.safe_to_operate:
        decision["release_action"] = "block"
    elif signal.severity in {"high", "medium"}:
        decision["release_action"] = "review"
    else:
        decision["release_action"] = "continue"

    return decision


def main() -> None:
    sample = {
        "stale_write_rejected_total": 3,
        "lease_takeover_total": 2,
        "retry_total": 1,
        "duplicate_commit_total": 0,
        "claim_latency_ms": 12.5,
    }
    out = decide(sample)
    Path("docs/operator").mkdir(parents=True, exist_ok=True)
    Path("docs/operator/sample_decision.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
