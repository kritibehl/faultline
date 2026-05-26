from __future__ import annotations

import json
from pathlib import Path
import matplotlib.pyplot as plt

data = json.loads(Path("reports/ops/multi_worker_stress_report.json").read_text())
runs = data["runs"]

workers = [r["workers"] for r in runs]
throughput = [r["throughput_jobs_per_sec"] for r in runs]
retry_amp = [r["retry_amplification_factor"] for r in runs]
queue_backlog = [r["queue_backlog"] for r in runs]
stale_rejections = [r["stale_worker_rejections"] for r in runs]
duplicate_rate = [r["duplicate_commit_rate_percent"] for r in runs]
contention = [r["contention_events"] for r in runs]

out = Path("reports/ops/benchmark_visuals")
out.mkdir(parents=True, exist_ok=True)

def save_plot(y, title, ylabel, filename):
    plt.figure(figsize=(9, 5))
    plt.plot(workers, y, marker="o")
    plt.title(title)
    plt.xlabel("worker count")
    plt.ylabel(ylabel)
    plt.xticks(workers)
    plt.tight_layout()
    plt.savefig(out / filename, dpi=180)
    plt.close()

save_plot(
    throughput,
    "Faultline Throughput vs Worker Count",
    "jobs/sec",
    "throughput_vs_workers.png",
)

save_plot(
    retry_amp,
    "Faultline Retry Amplification vs Worker Count",
    "retry amplification factor",
    "retry_amplification_vs_workers.png",
)

save_plot(
    queue_backlog,
    "Faultline Queue Backlog vs Worker Count",
    "queued jobs",
    "queue_depth_vs_workers.png",
)

save_plot(
    stale_rejections,
    "Faultline Stale-Worker Rejections vs Worker Count",
    "rejected stale writes",
    "stale_write_prevention_vs_workers.png",
)

save_plot(
    contention,
    "Faultline Lease Contention vs Worker Count",
    "contention events",
    "lease_contention_vs_workers.png",
)

save_plot(
    duplicate_rate,
    "Faultline Duplicate Commit Rate Under Stress",
    "duplicate commit rate %",
    "duplicate_commit_prevention_vs_workers.png",
)

summary = {
    "visual_pack": "faultline_worker_stress_benchmark_visuals",
    "worker_profiles": workers,
    "charts": [
        "throughput_vs_workers.png",
        "retry_amplification_vs_workers.png",
        "queue_depth_vs_workers.png",
        "stale_write_prevention_vs_workers.png",
        "lease_contention_vs_workers.png",
        "duplicate_commit_prevention_vs_workers.png"
    ],
    "key_takeaway": "as worker count rises, contention/retries/backlog increase while duplicate commit rate remains 0.0%",
    "safe_claim": "synthetic operational benchmark visualization pack, not production-scale benchmark"
}

(out / "benchmark_visual_pack_summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
