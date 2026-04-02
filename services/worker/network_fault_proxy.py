from __future__ import annotations

import random
import time
from typing import Any

import psycopg2
from psycopg2 import OperationalError

from services.worker.network_profiles import (
    FaultConfig,
    DNSFailure,
    HandshakeFailure,
    NetworkFaultInjector,
    PartialPartition,
    QueryTimeout,
)

FAULT_CLEAN = FaultConfig(drop_rate=0.0, latency_ms=0, timeout_rate=0.0, enabled=True)
FAULT_LOW = FaultConfig(drop_rate=0.05, latency_ms=0, timeout_rate=0.0, enabled=True)
FAULT_MEDIUM = FaultConfig(drop_rate=0.10, latency_ms=(25, 50), timeout_rate=0.05, enabled=True)
FAULT_HIGH = FaultConfig(drop_rate=0.20, latency_ms=(50, 100), timeout_rate=0.10, enabled=True)
FAULT_DROP = FaultConfig(drop_rate=1.0, latency_ms=0, timeout_rate=0.0, enabled=True)
FAULT_TIMEOUT = FaultConfig(drop_rate=0.0, latency_ms=0, timeout_rate=1.0, enabled=True)
FAULT_LATENCY = FaultConfig(drop_rate=0.0, latency_ms=(50, 100), timeout_rate=0.0, enabled=True)


def _ensure_counters(cfg: FaultConfig) -> None:
    if not hasattr(cfg, "total_queries"):
        cfg.total_queries = 0
    if not hasattr(cfg, "injected_drops"):
        cfg.injected_drops = 0
    if not hasattr(cfg, "injected_timeouts"):
        cfg.injected_timeouts = 0
    if not hasattr(cfg, "injected_latency_events"):
        cfg.injected_latency_events = 0


def _normalize_latency_ms(latency_ms: tuple[int, int] | int) -> tuple[int, int]:
    if isinstance(latency_ms, tuple):
        return latency_ms
    return (latency_ms, latency_ms)


def _classify_sql(sql: str | None) -> str:
    if not sql:
        return "query"
    q = " ".join(str(sql).lower().split())

    if "update jobs" in q and "lease_owner" in q and "fencing_token" in q:
        return "claim"
    if "heartbeat" in q or "lease_expires_at" in q:
        return "heartbeat"
    if "insert into ledger_entries" in q or "commit" in q:
        return "commit"
    if "select 1" in q:
        return "health"
    return "query"


class FaultCursor:
    def __init__(self, inner_cursor: Any, fault_config: FaultConfig, rng: random.Random):
        self._inner = inner_cursor
        self._config = fault_config
        self._rng = rng
        _ensure_counters(self._config)

    def _maybe_impair(self, operation: str) -> None:
        if not self._config.enabled:
            return

        low, high = _normalize_latency_ms(self._config.latency_ms)
        if high > 0:
            delay_ms = low if low == high else self._rng.randint(low, high)
            time.sleep(delay_ms / 1000.0)
            self._config.injected_latency_events += 1

        if self._config.timeout_rate > 0 and self._rng.random() < self._config.timeout_rate:
            self._config.injected_timeouts += 1
            raise OperationalError(f"fault_proxy: simulated timeout during {operation}")

        if self._config.drop_rate > 0 and self._rng.random() < self._config.drop_rate:
            self._config.injected_drops += 1
            raise OperationalError(f"fault_proxy: simulated connection drop during {operation}")

    def execute(self, sql: str, params: Any = None):
        operation = _classify_sql(sql)
        self._config.total_queries += 1
        self._maybe_impair(operation)
        if params is None:
            return self._inner.execute(sql)
        return self._inner.execute(sql, params)

    def executemany(self, sql: str, param_list: Any):
        operation = _classify_sql(sql)
        self._config.total_queries += 1
        self._maybe_impair(operation)
        return self._inner.executemany(sql, param_list)

    def __enter__(self):
        self._inner.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        return self._inner.__exit__(exc_type, exc, tb)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


class FaultConnection:
    def __init__(self, inner_conn: Any, fault_config: FaultConfig):
        self._inner = inner_conn
        self._config = fault_config
        self._rng = random.Random(fault_config.seed)
        _ensure_counters(self._config)

    def cursor(self, *args, **kwargs):
        inner_cursor = self._inner.cursor(*args, **kwargs)
        return FaultCursor(inner_cursor, self._config, self._rng)

    def commit(self):
        if self._config.enabled and self._config.drop_rate > 0 and self._rng.random() < self._config.drop_rate:
            self._config.injected_drops += 1
            raise OperationalError("fault_proxy: simulated connection drop during commit")
        return self._inner.commit()

    def rollback(self):
        return self._inner.rollback()

    def close(self):
        return self._inner.close()

    def __enter__(self):
        self._inner.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        return self._inner.__exit__(exc_type, exc, tb)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


class FaultProxy:
    @staticmethod
    def connect(dsn: str, fault_config: FaultConfig) -> FaultConnection:
        _ensure_counters(fault_config)
        rng = random.Random(fault_config.seed)

        low, high = _normalize_latency_ms(fault_config.latency_ms)
        if fault_config.enabled and high > 0:
            delay_ms = low if low == high else rng.randint(low, high)
            time.sleep(delay_ms / 1000.0)

        if fault_config.enabled and fault_config.timeout_rate > 0 and rng.random() < fault_config.timeout_rate:
            fault_config.injected_timeouts += 1
            raise OperationalError("fault_proxy: simulated timeout during connect")

        conn = psycopg2.connect(dsn)
        return FaultConnection(conn, fault_config)


class NetworkFaultProxy:
    def __init__(self, profile: str | None = None, seed: int | None = None):
        self.injector = NetworkFaultInjector(profile=profile, seed=seed)

    def on_connect(self):
        return self.injector.before_operation("connect")

    def on_claim(self):
        return self.injector.before_operation("claim")

    def on_heartbeat(self):
        return self.injector.before_operation("heartbeat")

    def on_commit(self):
        return self.injector.before_operation("commit")


__all__ = [
    "FaultConfig",
    "FaultProxy",
    "FaultConnection",
    "FaultCursor",
    "NetworkFaultProxy",
    "FAULT_CLEAN",
    "FAULT_LOW",
    "FAULT_MEDIUM",
    "FAULT_HIGH",
    "FAULT_DROP",
    "FAULT_TIMEOUT",
    "FAULT_LATENCY",
    "DNSFailure",
    "HandshakeFailure",
    "PartialPartition",
    "QueryTimeout",
]
