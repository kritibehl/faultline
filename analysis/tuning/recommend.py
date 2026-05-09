from __future__ import annotations

import json
from pathlib import Path


def recommend(metrics: dict) -> dict:
    jobs = int(metrics.get("jobs", 200))
    workers = int(metrics.get("workers", 8))
    retry_rate = float(metrics.get("retry_rate", 0.0))
    lease_takeovers = int(metrics.get("lease_takeover_total", 0))
    claim_latency_ms = float(metrics.get("claim_latency_ms", 0.0))

    batch_size = 10 if jobs >= 200 and claim_latency_ms >= 10 else 5
    poll_interval_ms = 100 if retry_rate < 0.05 else 250
    lease_duration_seconds = 30

    reasons = []

    if lease_takeovers > 0:
        lease_duration_seconds = 60
        reasons.append("lease takeovers observed; increase lease duration to reduce premature reclaim")

    if claim_latency_ms >= 10:
        reasons.append("claim latency observed; use batching to reduce coordinator round trips")
    else:
        reasons.append("claim latency is low; avoid excessive batching to preserve fairness")

    if retry_rate >= 0.05:
        reasons.append("retry rate elevated; slow polling/backoff to reduce retry amplification")

    return {
        "recommended_batch_size": batch_size,
        "recommended_poll_interval_ms": poll_interval_ms,
        "recommended_lease_duration_seconds": lease_duration_seconds,
        "reasons": reasons,
    }


def main() -> None:
    sample = {
        "jobs": 200,
        "workers": 8,
        "retry_rate": 0.02,
        "lease_takeover_total": 2,
        "claim_latency_ms": 12.5,
    }
    out = recommend(sample)
    Path("docs/operator").mkdir(parents=True, exist_ok=True)
    Path("docs/operator/tuning_recommendation.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
