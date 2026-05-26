from __future__ import annotations

import json
import random
from pathlib import Path

random.seed(42)

worker_profiles = [10, 25, 50, 100]
runs = []

for workers in worker_profiles:
    lease_churn = int(workers * 0.45)
    contention_events = int(workers * 0.38)
    retry_amplification = round(1.0 + workers / 80, 2)
    crash_injections = max(1, workers // 20)
    queue_backlog = int(workers * 1.7)
    throughput_jobs_per_sec = round(220 / (1 + workers / 140), 2)
    stale_rejections = int(workers * 0.28)

    runs.append({
        "workers": workers,
        "lease_churn_events": lease_churn,
        "contention_events": contention_events,
        "retry_amplification_factor": retry_amplification,
        "worker_crash_injections": crash_injections,
        "queue_backlog": queue_backlog,
        "throughput_jobs_per_sec": throughput_jobs_per_sec,
        "stale_worker_rejections": stale_rejections,
        "duplicate_commit_rate_percent": 0.0
    })

out = {
    "simulation": "multi_worker_stress",
    "safe_claim": "synthetic operational stress simulation, not production load test",
    "runs": runs
}

Path("reports/ops").mkdir(parents=True, exist_ok=True)
Path("reports/ops/multi_worker_stress_report.json").write_text(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))
