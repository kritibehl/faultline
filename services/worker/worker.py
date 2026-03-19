from __future__ import annotations

import os
import sys
import time
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from prometheus_client import start_http_server

from services.worker import metrics
from services.worker.network_fault_proxy import (
    DNSFailure,
    HandshakeFailure,
    NetworkFaultProxy,
    PartialPartition,
    QueryTimeout,
)
from services.worker.remediation import RemediationState


def connect_db(proxy: NetworkFaultProxy) -> None:
    proxy.on_connect()


def claim_job(proxy: NetworkFaultProxy) -> None:
    proxy.on_claim()


def heartbeat(proxy: NetworkFaultProxy) -> None:
    proxy.on_heartbeat()


def commit_job(proxy: NetworkFaultProxy) -> None:
    proxy.on_commit()


def main() -> None:
    metrics_port = int(os.getenv("FAULTLINE_METRICS_PORT", "9108"))
    start_http_server(metrics_port)

    proxy = NetworkFaultProxy()
    remediation = RemediationState()

    while True:
        now_quarantined = remediation.is_quarantined()
        now_degraded = remediation.is_degraded()

        metrics.worker_quarantined.set(1 if now_quarantined else 0)
        metrics.worker_degraded_mode.set(1 if now_degraded else 0)

        if now_quarantined:
            time.sleep(1.0)
            continue

        try:
            connect_db(proxy)
            claim_job(proxy)
            heartbeat(proxy)
            commit_job(proxy)

            had_active_partition = remediation.recent_partition_started_at is not None
            remediation.record_success()

            if had_active_partition:
                duration = remediation.note_partition_recovered()
                if duration is not None:
                    metrics.partition_recovery_seconds.observe(duration)
                    metrics.median_partition_recovery_seconds.set(
                        remediation.median_partition_recovery_seconds()
                    )

            time.sleep(0.2 if not now_degraded else 0.5)

        except DNSFailure:
            metrics.db_connect_failures_total.inc()
            metrics.reconnect_attempts_total.inc()
            remediation.record_failure()

        except HandshakeFailure:
            metrics.db_connect_failures_total.inc()
            metrics.reconnect_attempts_total.inc()
            remediation.record_failure()

        except QueryTimeout:
            metrics.query_timeout_total.inc()
            remediation.record_failure()

        except PartialPartition:
            metrics.lease_steal_attempts_total.inc()
            remediation.note_partition_start()
            remediation.record_failure()

        if remediation.consecutive_transport_failures >= 2 and not remediation.is_quarantined():
            remediation.enter_degraded_mode(6)

        if remediation.consecutive_transport_failures >= 4 and not remediation.is_quarantined():
            time.sleep(remediation.adaptive_backoff_seconds(base=0.15, cap=1.5))

        if remediation.consecutive_transport_failures >= 6 and not remediation.is_quarantined():
            remediation.quarantine(4)


if __name__ == "__main__":
    main()
