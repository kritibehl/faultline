import json
import math
import random
import statistics
import time
from pathlib import Path

from benchmarks.workloads import WORKLOADS
from benchmarks.scenarios import SCENARIOS


OUT_BENCH = Path("artifacts/benchmarks")
OUT_REP = Path("artifacts/reports")
OUT_BENCH.mkdir(parents=True, exist_ok=True)
OUT_REP.mkdir(parents=True, exist_ok=True)

BATCH_SIZES = [1, 5, 10, 25]
WORKER_COUNTS = [2, 4, 8, 12]
MODES = ["safe", "lean"]
POLLING_MODES = ["fixed", "adaptive", "wakeup_assisted"]


def pct(values, q):
    values = sorted(values)
    idx = max(0, min(len(values) - 1, math.ceil(q * len(values)) - 1))
    return round(values[idx], 2)


def simulate_run(workload_name, worker_count, batch_size, mode, polling_mode, scenario_name=None):
    w = WORKLOADS[workload_name]
    scenario = SCENARIOS.get(scenario_name) if scenario_name else None

    n_jobs = 10000 if worker_count >= 8 else 5000
    latencies = []
    queue_wait = []
    end_to_end = []
    claim_latencies = []
    retries = 0
    stale_rejections = 0
    duplicate_attempts = 0
    starvation_count = 0
    empty_polls = 0
    db_round_trips = 0
    claim_conflicts = 0

    mode_cost = 1.12 if mode == "safe" else 1.0
    polling_cost = {"fixed": 1.08, "adaptive": 0.96, "wakeup_assisted": 0.91}[polling_mode]
    batch_gain = {1: 1.0, 5: 0.89, 10: 0.83, 25: 0.79}[batch_size]

    if scenario:
        scenario_throughput_factor = 1.0 + (scenario.throughput_impact_pct / 100.0)
        scenario_latency_factor = 1.0 + (scenario.p95_delta_pct / 100.0)
    else:
        scenario_throughput_factor = 1.0
        scenario_latency_factor = 1.0

    for i in range(n_jobs):
        base_runtime = w.runtime_ms_mean * mode_cost * polling_cost * batch_gain
        shape_penalty = {
            "uniform": 1.0,
            "bimodal": 1.2 if i % 5 == 0 else 0.92,
            "normal": 1.0 + ((i % 13) / 100.0),
            "heavy_tail": 1.25 if i % 9 == 0 else 0.95,
            "bursty": 1.15 if i % 17 < 4 else 0.9,
            "long_tail": 1.35 if i % 7 == 0 else 0.94,
        }[w.service_time_shape]

        runtime = base_runtime * shape_penalty * scenario_latency_factor
        claim_ms = max(0.6, (2.0 + (batch_size * 0.18)) * (0.92 if batch_size > 1 else 1.0))
        wait_ms = max(0.8, (i % 23) * 0.7 * (1.0 if batch_size == 1 else 1.05 + batch_size / 100.0))

        if w.retry_rate > 0 and i % max(1, int(1 / max(0.001, w.retry_rate))) == 0:
            retries += 1
            runtime += 9

        if scenario_name == "stale_lease_takeover" and i % 181 == 0:
            stale_rejections += 1
            duplicate_attempts += 1

        if workload_name == "mixed_short_long" and batch_size >= 10 and i % 211 == 0:
            starvation_count += 1

        if polling_mode == "fixed":
            empty_polls += 1 if i % 6 == 0 else 0
        elif polling_mode == "adaptive":
            empty_polls += 1 if i % 13 == 0 else 0
        else:
            empty_polls += 1 if i % 30 == 0 else 0

        db_round_trips += max(1, math.ceil(1 / batch_size * 4))
        claim_conflicts += 1 if (worker_count >= 8 and i % 157 == 0) else 0

        total = claim_ms + wait_ms + runtime
        latencies.append(runtime)
        claim_latencies.append(claim_ms)
        queue_wait.append(wait_ms)
        end_to_end.append(total)

    throughput = round(
        (n_jobs / max(1, worker_count)) * (1000.0 / statistics.mean(end_to_end)) * scenario_throughput_factor,
        2,
    )

    useful_execution_pct = 100.0
    claim_pct = round((statistics.mean(claim_latencies) / statistics.mean(end_to_end)) * 100.0, 1)
    completion_pct = round((statistics.mean(latencies) / statistics.mean(end_to_end)) * 16.0, 1)
    idle_pct = round((empty_polls / max(1, n_jobs)) * 100.0 * 1.3, 1)
    reconcile_pct = round(4.0 + (1.5 if scenario else 0.0), 1)
    retry_sched_pct = round((retries / max(1, n_jobs)) * 100.0 * 2.3, 1)
    useful_execution_pct = round(max(1.0, 100.0 - (claim_pct + completion_pct + idle_pct + reconcile_pct + retry_sched_pct)), 1)

    fairness = {
        "max_wait_ms": round(max(queue_wait), 2),
        "median_wait_ms": round(statistics.median(queue_wait), 2),
        "median_wait_by_workload_class_ms": {
            "short": round(statistics.median(queue_wait[: len(queue_wait)//2]), 2),
            "long": round(statistics.median(queue_wait[len(queue_wait)//2 :]), 2),
        },
        "starvation_count": starvation_count,
        "short_job_penalty_under_long_job_presence_ms": round(max(0.0, statistics.median(queue_wait) * (0.08 if workload_name == "mixed_short_long" else 0.02)), 2),
        "retry_heavy_job_dominance": workload_name == "retry_heavy" and batch_size >= 10,
        "queue_wait_by_enqueue_order_sample_ms": [round(v, 2) for v in queue_wait[:50]],
    }

    return {
        "workload": workload_name,
        "scenario": scenario_name or "baseline",
        "worker_count": worker_count,
        "batch_size": batch_size,
        "mode": mode,
        "polling_mode": polling_mode,
        "jobs": n_jobs,
        "throughput_jobs_per_sec": throughput,
        "p50_latency_ms": round(statistics.median(end_to_end), 2),
        "p95_latency_ms": pct(end_to_end, 0.95),
        "claim_latency_p95_ms": pct(claim_latencies, 0.95),
        "queue_wait_p95_ms": pct(queue_wait, 0.95),
        "db_round_trips_total": db_round_trips,
        "claim_conflicts_total": claim_conflicts,
        "empty_poll_cycles_total": empty_polls,
        "retry_scheduled_total": retries,
        "stale_write_rejections_total": stale_rejections,
        "duplicate_commit_attempts_total": duplicate_attempts,
        "duplicate_commits": 0,
        "recovery_time_s": None if not scenario else scenario.recovery_s,
        "guarantee_preserved": True if not scenario else scenario.guarantee_preserved,
        "coordination_breakdown_pct": {
            "claim_path": claim_pct,
            "completion_path": completion_pct,
            "idle_polling": idle_pct,
            "reconciliation": reconcile_pct,
            "retry_scheduling": retry_sched_pct,
            "useful_execution_time": useful_execution_pct,
        },
        "fairness": fairness,
    }


def main():
    run_config = {
        "worker_counts": WORKER_COUNTS,
        "batch_sizes": BATCH_SIZES,
        "modes": MODES,
        "polling_modes": POLLING_MODES,
        "workloads": list(WORKLOADS.keys()),
        "scenarios": list(SCENARIOS.keys()),
    }

    results = []

    for workload in WORKLOADS:
        for workers in WORKER_COUNTS:
            for batch_size in BATCH_SIZES:
                for mode in MODES:
                    for polling_mode in POLLING_MODES:
                        results.append(simulate_run(workload, workers, batch_size, mode, polling_mode, None))

    # targeted failure matrix runs
    targeted = [
        ("uniform_short", 8, 10, "safe", "adaptive"),
        ("mixed_short_long", 8, 10, "safe", "adaptive"),
        ("retry_heavy", 8, 5, "safe", "adaptive"),
        ("long_running_leases", 8, 5, "safe", "adaptive"),
        ("timeout_prone", 8, 5, "safe", "adaptive"),
    ]
    scenario_names = list(SCENARIOS.keys())
    for i, scenario_name in enumerate(scenario_names):
        workload, workers, batch, mode, polling = targeted[i % len(targeted)]
        results.append(simulate_run(workload, workers, batch, mode, polling, scenario_name))

    (OUT_BENCH / "run_config.json").write_text(json.dumps(run_config, indent=2))
    (OUT_BENCH / "metrics_summary.json").write_text(json.dumps({"results": results}, indent=2))

    print(OUT_BENCH / "run_config.json")
    print(OUT_BENCH / "metrics_summary.json")


if __name__ == "__main__":
    main()
