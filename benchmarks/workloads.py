from dataclasses import dataclass


@dataclass(frozen=True)
class WorkloadProfile:
    name: str
    runtime_ms_mean: float
    runtime_ms_p95: float
    payload_kb: int
    failure_probability: float
    retry_rate: float
    service_time_shape: str


WORKLOADS = {
    "uniform_short": WorkloadProfile("uniform_short", 18, 28, 4, 0.003, 0.01, "uniform"),
    "mixed_short_long": WorkloadProfile("mixed_short_long", 42, 145, 8, 0.006, 0.03, "bimodal"),
    "large_payload": WorkloadProfile("large_payload", 55, 120, 256, 0.004, 0.02, "normal"),
    "retry_heavy": WorkloadProfile("retry_heavy", 26, 70, 6, 0.02, 0.12, "uniform"),
    "timeout_prone": WorkloadProfile("timeout_prone", 75, 180, 10, 0.035, 0.08, "heavy_tail"),
    "burst_enqueue": WorkloadProfile("burst_enqueue", 22, 48, 5, 0.005, 0.02, "bursty"),
    "long_running_leases": WorkloadProfile("long_running_leases", 120, 280, 12, 0.01, 0.05, "long_tail"),
}
