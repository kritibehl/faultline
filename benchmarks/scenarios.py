from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    name: str
    throughput_impact_pct: float
    p95_delta_pct: float
    recovery_s: float
    guarantee_preserved: bool
    operator_recommendation: str


SCENARIOS = {
    "worker_crash_before_completion_write": Scenario(
        "worker_crash_before_completion_write", -12.0, 9.0, 1.1, True,
        "validate reclaim path and inspect lease expiry/reconcile timing",
    ),
    "worker_crash_after_result_before_commit": Scenario(
        "worker_crash_after_result_before_commit", -8.0, 6.0, 0.8, True,
        "inspect stale-write rejection and commit fencing evidence",
    ),
    "stale_lease_takeover": Scenario(
        "stale_lease_takeover", -4.0, 3.0, 0.4, True,
        "review fencing token advancement and stale writer rejection",
    ),
    "db_reconnect_failure": Scenario(
        "db_reconnect_failure", -15.0, 12.0, 1.7, True,
        "increase reconnect backoff and validate retry jitter",
    ),
    "query_timeout_burst": Scenario(
        "query_timeout_burst", -18.0, 14.0, 2.3, True,
        "inspect timeout burst handling and widen retry backoff",
    ),
    "intermittent_db_latency": Scenario(
        "intermittent_db_latency", -10.0, 18.0, 1.5, True,
        "enable adaptive polling and review claim path DB cost",
    ),
    "retry_storm_under_transient_error": Scenario(
        "retry_storm_under_transient_error", -22.0, 21.0, 2.8, True,
        "reduce retry aggressiveness and add jitter",
    ),
    "long_job_exceeding_nominal_lease": Scenario(
        "long_job_exceeding_nominal_lease", -7.0, 8.0, 0.9, True,
        "increase lease duration or add lease renewal margin",
    ),
    "lease_reaper_reclaim_under_load": Scenario(
        "lease_reaper_reclaim_under_load", -9.0, 10.0, 1.0, True,
        "review reaper cadence and batch reclaim behavior",
    ),
}
