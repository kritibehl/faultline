from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

db_connect_failures_total = Counter(
    "faultline_db_connect_failures_total",
    "DB connect failures",
)

reconnect_attempts_total = Counter(
    "faultline_reconnect_attempts_total",
    "Reconnect attempts",
)

query_timeout_total = Counter(
    "faultline_query_timeout_total",
    "Query timeout count",
)

lease_steal_attempts_total = Counter(
    "faultline_lease_steal_attempts_total",
    "Lease steal attempts",
)

partition_recovery_seconds = Histogram(
    "faultline_partition_recovery_seconds",
    "Partition recovery duration seconds",
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)

median_partition_recovery_seconds = Gauge(
    "faultline_median_partition_recovery_seconds",
    "Median partition recovery seconds",
)

worker_quarantined = Gauge(
    "faultline_worker_quarantined",
    "Whether worker is quarantined",
)

worker_degraded_mode = Gauge(
    "faultline_worker_degraded_mode",
    "Whether worker is in degraded mode",
)
