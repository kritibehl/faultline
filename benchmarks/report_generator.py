import json
from pathlib import Path

bench = json.loads(Path("artifacts/benchmarks/metrics_summary.json").read_text())["results"]

baseline = [r for r in bench if r["scenario"] == "baseline"]
failure_runs = [r for r in bench if r["scenario"] != "baseline"]

# coordination breakdown
avg_breakdown = {
    "claim_path": 0.0,
    "completion_path": 0.0,
    "idle_polling": 0.0,
    "reconciliation": 0.0,
    "retry_scheduling": 0.0,
    "useful_execution_time": 0.0,
}
for r in baseline:
    for k, v in r["coordination_breakdown_pct"].items():
        avg_breakdown[k] += v
for k in avg_breakdown:
    avg_breakdown[k] = round(avg_breakdown[k] / max(1, len(baseline)), 1)

Path("artifacts/reports/coordination_breakdown.md").write_text(
f"""# Coordination Cost Breakdown

- claim path: {avg_breakdown['claim_path']}%
- completion path: {avg_breakdown['completion_path']}%
- idle polling: {avg_breakdown['idle_polling']}%
- reconciliation: {avg_breakdown['reconciliation']}%
- retry scheduling: {avg_breakdown['retry_scheduling']}%
- useful execution time: {avg_breakdown['useful_execution_time']}%
"""
)

# fairness report
worst = max(baseline, key=lambda r: r["fairness"]["max_wait_ms"])
fairness_md = f"""# Fairness Report

## Summary
- worst max wait: {worst['fairness']['max_wait_ms']} ms
- median wait: {worst['fairness']['median_wait_ms']} ms
- starvation count: {worst['fairness']['starvation_count']}
- short-job penalty: {worst['fairness']['short_job_penalty_under_long_job_presence_ms']} ms
- retry-heavy dominance observed: {worst['fairness']['retry_heavy_job_dominance']}

## Notes
This report captures queue wait by enqueue order, median wait by workload class, starvation count, short-job penalty under long-job presence, and retry-heavy dominance.
"""
Path("artifacts/reports/fairness_report.md").write_text(fairness_md)
Path("artifacts/reports/scheduler_behavior.json").write_text(
    json.dumps(
        {
            "worst_case": worst["fairness"],
            "workload": worst["workload"],
            "batch_size": worst["batch_size"],
            "worker_count": worst["worker_count"],
        },
        indent=2,
    )
)

# failure matrix
lines = []
lines.append("# Failure Matrix\n")
lines.append("| Scenario | Injected | Guarantee preserved | Throughput impact | p95 latency delta | Recovery | Operator recommendation |")
lines.append("|---|---|---|---:|---:|---:|---|")
for r in failure_runs:
    baseline_match = next(
        b for b in baseline
        if b["workload"] == r["workload"]
        and b["worker_count"] == r["worker_count"]
        and b["batch_size"] == r["batch_size"]
        and b["mode"] == r["mode"]
        and b["polling_mode"] == r["polling_mode"]
    )
    throughput_delta = round(((r["throughput_jobs_per_sec"] - baseline_match["throughput_jobs_per_sec"]) / baseline_match["throughput_jobs_per_sec"]) * 100.0, 1)
    p95_delta = round(((r["p95_latency_ms"] - baseline_match["p95_latency_ms"]) / baseline_match["p95_latency_ms"]) * 100.0, 1)
    recommendation = {
        "worker_crash_before_completion_write": "validate reclaim path and lease expiry timing",
        "worker_crash_after_result_before_commit": "inspect stale-write rejection evidence",
        "stale_lease_takeover": "review fencing token advancement",
        "db_reconnect_failure": "increase reconnect backoff",
        "query_timeout_burst": "widen retry backoff",
        "intermittent_db_latency": "enable adaptive polling",
        "retry_storm_under_transient_error": "reduce retry aggressiveness",
        "long_job_exceeding_nominal_lease": "increase lease duration",
        "lease_reaper_reclaim_under_load": "review reaper cadence",
    }[r["scenario"]]
    lines.append(f"| {r['scenario']} | yes | {r['guarantee_preserved']} | {throughput_delta}% | {p95_delta}% | {r['recovery_time_s']}s | {recommendation} |")
Path("artifacts/reports/failure_matrix.md").write_text("\n".join(lines) + "\n")

print("artifacts/reports/coordination_breakdown.md")
print("artifacts/reports/fairness_report.md")
print("artifacts/reports/scheduler_behavior.json")
print("artifacts/reports/failure_matrix.md")
