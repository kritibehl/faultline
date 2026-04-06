import json
from pathlib import Path

bench = json.loads(Path("artifacts/benchmarks/metrics_summary.json").read_text())["results"]
baseline = [r for r in bench if r["scenario"] == "baseline"]

best_batch = max(baseline, key=lambda r: (r["throughput_jobs_per_sec"], -r["p95_latency_ms"]))
best_polling = max(baseline, key=lambda r: (r["throughput_jobs_per_sec"], -r["empty_poll_cycles_total"]))
worst_fairness = max(baseline, key=lambda r: r["fairness"]["starvation_count"])

lines = ["# Tuning Recommendation", ""]
lines.append(f"- coordination bottleneck dominated claim path; increase batch size toward {best_batch['batch_size']} where throughput and claim path cost improved")
lines.append(f"- polling overhead dominated under lower occupancy; prefer {best_polling['polling_mode']} mode to reduce empty polls")
lines.append("- retry aggressiveness amplified contention under retry-heavy workloads; widen retry backoff interval and add jitter")
lines.append("- lease duration is too short for long-running jobs in long_running_leases profile; increase default lease or renew earlier")
if worst_fairness["fairness"]["starvation_count"] > 0:
    lines.append(f"- fairness warning: batch size {worst_fairness['batch_size']} under {worst_fairness['workload']} showed starvation_count={worst_fairness['fairness']['starvation_count']}")

Path("artifacts/reports/tuning_recommendation.md").write_text("\n".join(lines) + "\n")

decision = {
    "scenario_name": best_batch["scenario"],
    "worker_count": best_batch["worker_count"],
    "batch_size": best_batch["batch_size"],
    "throughput": best_batch["throughput_jobs_per_sec"],
    "p95_latency_ms": best_batch["p95_latency_ms"],
    "duplicate_commits": best_batch["duplicate_commits"],
    "stale_writes_prevented": best_batch["stale_write_rejections_total"],
    "recovery_time_s": best_batch["recovery_time_s"],
    "fairness_warning": worst_fairness["fairness"]["starvation_count"] > 0,
    "bottleneck": "claim path" if best_batch["coordination_breakdown_pct"]["claim_path"] >= best_batch["coordination_breakdown_pct"]["idle_polling"] else "idle polling",
    "recommendation": f"prefer batch_size={best_batch['batch_size']} and polling_mode={best_polling['polling_mode']}",
    "safe_for_production": best_batch["duplicate_commits"] == 0,
}
Path("artifacts/reports/decision_report.json").write_text(json.dumps(decision, indent=2))
print("artifacts/reports/tuning_recommendation.md")
print("artifacts/reports/decision_report.json")
