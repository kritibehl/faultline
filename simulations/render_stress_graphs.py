from __future__ import annotations

import json
from pathlib import Path
import matplotlib.pyplot as plt

data = json.loads(Path("reports/ops/multi_worker_stress_report.json").read_text())
runs = data["runs"]

workers = [r["workers"] for r in runs]
throughput = [r["throughput_jobs_per_sec"] for r in runs]
contention = [r["contention_events"] for r in runs]
backlog = [r["queue_backlog"] for r in runs]
stale = [r["stale_worker_rejections"] for r in runs]

Path("reports/ops").mkdir(parents=True, exist_ok=True)

plt.figure(figsize=(9, 5))
plt.plot(workers, throughput, marker="o")
plt.title("Faultline Throughput Under Worker Stress")
plt.xlabel("workers")
plt.ylabel("jobs/sec")
plt.tight_layout()
plt.savefig("reports/ops/throughput_graph.png", dpi=160)

plt.figure(figsize=(9, 5))
plt.plot(workers, contention, marker="o")
plt.title("Faultline Lease Contention Growth")
plt.xlabel("workers")
plt.ylabel("contention events")
plt.tight_layout()
plt.savefig("reports/ops/contention_graph.png", dpi=160)

plt.figure(figsize=(9, 5))
plt.plot(workers, backlog, marker="o")
plt.title("Faultline Queue Backlog Growth")
plt.xlabel("workers")
plt.ylabel("queued jobs")
plt.tight_layout()
plt.savefig("reports/ops/backlog_graph.png", dpi=160)

plt.figure(figsize=(9, 5))
plt.plot(workers, stale, marker="o")
plt.title("Faultline Stale-Worker Rejections")
plt.xlabel("workers")
plt.ylabel("rejections")
plt.tight_layout()
plt.savefig("reports/ops/stale_rejection_graph.png", dpi=160)

print("wrote reports/ops/*.png")
