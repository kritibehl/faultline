"""
network_fault_proxy.py — Network fault injection layer for Faultline.
Wraps psycopg2 connections to simulate latency, connection drops, timeouts.
"""
import random, time, logging
from dataclasses import dataclass, field
from typing import Optional, Tuple
import psycopg2

logger = logging.getLogger(__name__)

@dataclass
class FaultConfig:
    drop_rate: float = 0.0
    latency_ms: Tuple[int, int] = (0, 0)
    timeout_rate: float = 0.0
    seed: Optional[int] = None
    enabled: bool = True
    injected_drops: int = field(default=0, init=False, repr=False)
    injected_latency_events: int = field(default=0, init=False, repr=False)
    injected_timeouts: int = field(default=0, init=False, repr=False)
    total_queries: int = field(default=0, init=False, repr=False)

    def __post_init__(self):
        self._rng = random.Random(self.seed)

    def should_drop(self):
        return self.enabled and self._rng.random() < self.drop_rate

    def should_timeout(self):
        return self.enabled and self._rng.random() < self.timeout_rate

    def latency_seconds(self):
        if not self.enabled or self.latency_ms == (0, 0):
            return 0.0
        ms = self._rng.randint(self.latency_ms[0], self.latency_ms[1])
        return ms / 1000.0

    def summary(self):
        return {
            "total_queries": self.total_queries,
            "injected_drops": self.injected_drops,
            "injected_latency_events": self.injected_latency_events,
            "injected_timeouts": self.injected_timeouts,
            "drop_rate_configured": self.drop_rate,
            "timeout_rate_configured": self.timeout_rate,
            "latency_ms_range": self.latency_ms,
        }


class FaultCursor:
    def __init__(self, real_cursor, config):
        self._cur = real_cursor
        self._config = config

    def execute(self, query, params=None):
        self._config.total_queries += 1
        latency = self._config.latency_seconds()
        if latency > 0:
            self._config.injected_latency_events += 1
            time.sleep(latency)
        if self._config.should_drop():
            self._config.injected_drops += 1
            raise psycopg2.OperationalError("fault_proxy: simulated connection drop")
        if self._config.should_timeout():
            self._config.injected_timeouts += 1
            raise psycopg2.OperationalError("fault_proxy: simulated query timeout")
        return self._cur.execute(query, params)

    def fetchone(self): return self._cur.fetchone()
    def fetchall(self): return self._cur.fetchall()
    def fetchmany(self, size=None): return self._cur.fetchmany(size)
    @property
    def rowcount(self): return self._cur.rowcount
    @property
    def description(self): return self._cur.description
    @property
    def statusmessage(self): return getattr(self._cur, 'statusmessage', None)
    def close(self): return self._cur.close()
    def __enter__(self): return self
    def __exit__(self, *a): self.close(); return False
    def __iter__(self): return iter(self._cur)


class FaultConnection:
    def __init__(self, real_conn, config):
        self._conn = real_conn
        self._config = config

    def cursor(self, *args, **kwargs):
        return FaultCursor(self._conn.cursor(*args, **kwargs), self._config)

    def commit(self): return self._conn.commit()
    def rollback(self): return self._conn.rollback()
    def close(self): return self._conn.close()
    @property
    def closed(self): return self._conn.closed
    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None: self.commit()
        else: self.rollback()
        return False


class FaultProxy:
    @staticmethod
    def connect(dsn, config):
        return FaultConnection(psycopg2.connect(dsn), config)


FAULT_CLEAN  = FaultConfig(enabled=False)
FAULT_LOW    = FaultConfig(drop_rate=0.05, latency_ms=(5, 50),   timeout_rate=0.01, seed=42)
FAULT_MEDIUM = FaultConfig(drop_rate=0.10, latency_ms=(10, 100), timeout_rate=0.02, seed=42)
