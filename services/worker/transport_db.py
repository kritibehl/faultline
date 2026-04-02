from __future__ import annotations

import os
from typing import Any

from services.worker import metrics
from services.worker.network_fault_proxy import (
    DNSFailure,
    HandshakeFailure,
    NetworkFaultProxy,
    PartialPartition,
    QueryTimeout,
)
from services.worker.remediation import RemediationState

_PROXY = NetworkFaultProxy(
    profile=os.getenv("FAULTLINE_NETWORK_PROFILE"),
    seed=int(os.getenv("FAULTLINE_NETWORK_SEED", "7")),
)
_REMEDIATION = RemediationState()


def _maybe_record_recovery() -> None:
    duration = _REMEDIATION.note_partition_recovered()
    if duration is not None:
        metrics.partition_recovery_seconds.observe(duration)
        metrics.median_partition_recovery_seconds.set(
            _REMEDIATION.median_partition_recovery_seconds()
        )


def _record_success() -> None:
    had_active_partition = _REMEDIATION.recent_partition_started_at is not None
    _REMEDIATION.record_success()
    if had_active_partition:
        _maybe_record_recovery()


def _record_dns_failure() -> None:
    metrics.db_connect_failures_total.inc()
    metrics.reconnect_attempts_total.inc()
    _REMEDIATION.record_failure()


def _record_handshake_failure() -> None:
    metrics.db_connect_failures_total.inc()
    metrics.reconnect_attempts_total.inc()
    _REMEDIATION.record_failure()


def _record_query_timeout() -> None:
    metrics.query_timeout_total.inc()
    _REMEDIATION.record_failure()


def _record_partial_partition() -> None:
    metrics.lease_steal_attempts_total.inc()
    _REMEDIATION.note_partition_start()
    _REMEDIATION.record_failure()


def _refresh_state_gauges() -> None:
    metrics.worker_quarantined.set(1 if _REMEDIATION.is_quarantined() else 0)
    metrics.worker_degraded_mode.set(1 if _REMEDIATION.is_degraded() else 0)


def _apply_escalation() -> None:
    if _REMEDIATION.consecutive_transport_failures >= 2 and not _REMEDIATION.is_quarantined():
        _REMEDIATION.enter_degraded_mode(6)

    if _REMEDIATION.consecutive_transport_failures >= 6 and not _REMEDIATION.is_quarantined():
        _REMEDIATION.quarantine(4)


def _classify_sql(statement: str) -> str:
    s = " ".join(statement.lower().split())

    if "for update skip locked" in s or "skip locked" in s or "lease_owner" in s:
        return "claim"

    if "lease_expires_at" in s or "heartbeat" in s or ("update" in s and "lease_" in s):
        return "heartbeat"

    if (
        "status = 'done'" in s
        or 'status="done"' in s
        or "completed_at" in s
        or "finished_at" in s
        or ("update" in s and "status" in s)
    ):
        return "commit"

    return "query"


def _inject_before_operation(operation: str) -> None:
    _refresh_state_gauges()

    if _REMEDIATION.is_quarantined():
        raise PartialPartition("worker quarantined after repeated transport failures")

    if operation == "connect":
        _PROXY.on_connect()
    elif operation == "claim":
        _PROXY.on_claim()
    elif operation == "heartbeat":
        _PROXY.on_heartbeat()
    elif operation == "commit":
        _PROXY.on_commit()
    else:
        _PROXY.on_heartbeat()


class CursorProxy:
    def __init__(self, inner: Any):
        self._inner = inner

    def execute(self, statement: Any, *args: Any, **kwargs: Any):
        sql = statement.decode() if isinstance(statement, bytes) else str(statement)
        op = _classify_sql(sql)

        try:
            _inject_before_operation(op)
            result = self._inner.execute(statement, *args, **kwargs)
            _record_success()
            _refresh_state_gauges()
            return result
        except DNSFailure:
            _record_dns_failure()
            _apply_escalation()
            _refresh_state_gauges()
            raise
        except HandshakeFailure:
            _record_handshake_failure()
            _apply_escalation()
            _refresh_state_gauges()
            raise
        except QueryTimeout:
            _record_query_timeout()
            _apply_escalation()
            _refresh_state_gauges()
            raise
        except PartialPartition:
            _record_partial_partition()
            _apply_escalation()
            _refresh_state_gauges()
            raise

    def executemany(self, statement: Any, *args: Any, **kwargs: Any):
        sql = statement.decode() if isinstance(statement, bytes) else str(statement)
        op = _classify_sql(sql)

        try:
            _inject_before_operation(op)
            result = self._inner.executemany(statement, *args, **kwargs)
            _record_success()
            _refresh_state_gauges()
            return result
        except DNSFailure:
            _record_dns_failure()
            _apply_escalation()
            _refresh_state_gauges()
            raise
        except HandshakeFailure:
            _record_handshake_failure()
            _apply_escalation()
            _refresh_state_gauges()
            raise
        except QueryTimeout:
            _record_query_timeout()
            _apply_escalation()
            _refresh_state_gauges()
            raise
        except PartialPartition:
            _record_partial_partition()
            _apply_escalation()
            _refresh_state_gauges()
            raise

    def __enter__(self):
        entered = self._inner.__enter__()
        return CursorProxy(entered)

    def __exit__(self, exc_type, exc, tb):
        return self._inner.__exit__(exc_type, exc, tb)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


class ConnectionProxy:
    def __init__(self, inner: Any):
        self._inner = inner

    def cursor(self, *args: Any, **kwargs: Any):
        return CursorProxy(self._inner.cursor(*args, **kwargs))

    def __enter__(self):
        entered = self._inner.__enter__()
        return ConnectionProxy(entered)

    def __exit__(self, exc_type, exc, tb):
        return self._inner.__exit__(exc_type, exc, tb)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


def connect_db(*args: Any, **kwargs: Any):
    try:
        _inject_before_operation("connect")

        try:
            import psycopg
            conn = psycopg.connect(*args, **kwargs)
        except ImportError:
            import psycopg2
            conn = psycopg2.connect(*args, **kwargs)

        _record_success()
        _refresh_state_gauges()
        return ConnectionProxy(conn)

    except DNSFailure:
        _record_dns_failure()
        _apply_escalation()
        _refresh_state_gauges()
        raise
    except HandshakeFailure:
        _record_handshake_failure()
        _apply_escalation()
        _refresh_state_gauges()
        raise
    except Exception:
        metrics.db_connect_failures_total.inc()
        metrics.reconnect_attempts_total.inc()
        _REMEDIATION.record_failure()
        _apply_escalation()
        _refresh_state_gauges()
        raise


def get_conn():
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")
    if not database_url:
        raise RuntimeError("DATABASE_URL or POSTGRES_DSN must be set")
    return connect_db(database_url)