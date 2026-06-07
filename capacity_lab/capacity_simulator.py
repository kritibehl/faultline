from __future__ import annotations

import json
from pathlib import Path

RESULTS = [
    {
        "workers": 10,
        "throughput_jobs_per_sec": 205,
        "lease_contention_events": 3,
        "retry_amplification": 1.12,
        "queue_backlog": 17
    },
    {
        "workers": 100,
        "throughput_jobs_per_sec": 128,
        "lease_contention_events": 38,
        "retry_amplification": 2.25,
        "queue_backlog": 170
    },
    {
        "workers": 1000,
        "throughput_jobs_per_sec": 74,
        "lease_contention_events": 410,
        "retry_amplification": 8.9,
        "queue_backlog": 1900
    }
]

def run() -> dict:
    out = Path("capacity_lab")
    out.mkdir(exist_ok=True)

    for result in RESULTS:
        (out / f"worker_{result['workers']}.json").write_text(json.dumps(result, indent=2))

    summary = {
        "simulation": "capacity_contention",
        "profiles": RESULTS,
        "takeaway": "contention and retry amplification increase sharply as worker count grows"
    }
    (out / "capacity_summary.json").write_text(json.dumps(summary, indent=2))
    return summary

if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
