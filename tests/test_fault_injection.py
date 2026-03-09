"""
test_fault_injection.py — Tests for the network fault injection layer.
"""
import os, sys, time, uuid, hashlib, threading
from pathlib import Path
import psycopg2
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.worker.network_fault_proxy import (
    FaultConfig, FaultProxy, FaultConnection, FaultCursor,
    FAULT_CLEAN, FAULT_LOW, FAULT_MEDIUM,
)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://faultline:faultline@localhost:5432/faultline")

def real_conn(): return psycopg2.connect(DATABASE_URL)

def seed(key):
    jid = str(uuid.uuid4())
    h = hashlib.sha256(b"{}").hexdigest()
    with real_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ledger_entries WHERE job_id IN (SELECT id FROM jobs WHERE idempotency_key=%s)", (key,))
            cur.execute("DELETE FROM jobs WHERE idempotency_key=%s", (key,))
            cur.execute("INSERT INTO jobs (id,payload,payload_hash,state,attempts,max_attempts,idempotency_key,fencing_token,next_run_at) VALUES (%s,'{}' ,%s,'queued',0,3,%s,1,NOW())", (jid,h,key))
        conn.commit()
    return jid

def ledger_count(job_id):
    with real_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM ledger_entries WHERE job_id=%s::uuid", (job_id,))
            return cur.fetchone()[0]

def test_fault_proxy_connects():
    conn = FaultProxy.connect(DATABASE_URL, FAULT_CLEAN)
    assert isinstance(conn, FaultConnection)
    assert not conn.closed
    conn.close()

def test_fault_proxy_cursor_is_fault_cursor():
    conn = FaultProxy.connect(DATABASE_URL, FAULT_CLEAN)
    assert isinstance(conn.cursor(), FaultCursor)
    conn.close()

def test_fault_proxy_executes_cleanly():
    conn = FaultProxy.connect(DATABASE_URL, FAULT_CLEAN)
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)
    conn.close()

def test_drop_rate_1_always_raises():
    config = FaultConfig(drop_rate=1.0, seed=0)
    conn = FaultProxy.connect(DATABASE_URL, config)
    with pytest.raises(psycopg2.OperationalError, match="fault_proxy"):
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    conn.close()
    assert config.injected_drops == 1

def test_drop_rate_0_never_raises():
    config = FaultConfig(drop_rate=0.0, seed=0)
    conn = FaultProxy.connect(DATABASE_URL, config)
    with conn.cursor() as cur:
        for _ in range(20):
            cur.execute("SELECT 1")
    conn.close()
    assert config.injected_drops == 0

def test_latency_is_injected():
    config = FaultConfig(latency_ms=(50, 100), seed=0)
    conn = FaultProxy.connect(DATABASE_URL, config)
    start = time.monotonic()
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
    elapsed_ms = (time.monotonic() - start) * 1000
    conn.close()
    assert elapsed_ms >= 40, f"Expected >=40ms, got {elapsed_ms:.0f}ms"
    assert config.injected_latency_events == 1

def test_disabled_injects_nothing():
    config = FaultConfig(drop_rate=1.0, timeout_rate=1.0, enabled=False)
    conn = FaultProxy.connect(DATABASE_URL, config)
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)
    conn.close()
    assert config.injected_drops == 0

def test_counter_tracks_queries():
    config = FaultConfig(drop_rate=0.0, seed=0)
    conn = FaultProxy.connect(DATABASE_URL, config)
    with conn.cursor() as cur:
        for _ in range(5):
            cur.execute("SELECT 1")
    conn.close()
    assert config.total_queries == 5

def _race(job_id, fault_config):
    results = {}
    barrier = threading.Event()

    def worker_a():
        try:
            conn = FaultProxy.connect(DATABASE_URL, FaultConfig(drop_rate=fault_config.drop_rate, latency_ms=fault_config.latency_ms, timeout_rate=fault_config.timeout_rate, seed=fault_config.seed, enabled=fault_config.enabled))
            with conn.cursor() as cur:
                cur.execute("UPDATE jobs SET state='running', lease_owner='worker-a', lease_expires_at=NOW()+interval '50ms' WHERE id=%s::uuid AND state='queued'", (job_id,))
                if cur.rowcount == 0: results["a"] = "no_claim"; return
            conn.commit()
            barrier.set()
            time.sleep(0.12)
            with conn.cursor() as cur:
                cur.execute("SELECT fencing_token FROM jobs WHERE id=%s::uuid", (job_id,))
                row = cur.fetchone()
                if not row or row[0] != 1: results["a"] = "stale_blocked"; return
                try:
                    cur.execute("INSERT INTO ledger_entries (job_id,fencing_token,worker_id,written_at) VALUES (%s::uuid,1,'worker-a',NOW())", (job_id,))
                    conn.commit(); results["a"] = "committed"
                except (psycopg2.errors.UniqueViolation,):
                    conn.rollback(); results["a"] = "unique_blocked"
        except psycopg2.OperationalError: results["a"] = "fault_error"
        except Exception as e: results["a"] = f"error:{e}"

    def worker_b():
        barrier.wait(timeout=2.0)
        try:
            conn = FaultProxy.connect(DATABASE_URL, FaultConfig(drop_rate=fault_config.drop_rate, latency_ms=fault_config.latency_ms, timeout_rate=fault_config.timeout_rate, seed=fault_config.seed, enabled=fault_config.enabled))
            with conn.cursor() as cur:
                cur.execute("UPDATE jobs SET state='running', fencing_token=fencing_token+1, lease_owner='worker-b', lease_expires_at=NOW()+interval '30s' WHERE id=%s::uuid AND lease_expires_at < NOW()", (job_id,))
                if cur.rowcount == 0: results["b"] = "no_reclaim"; return
            conn.commit()
            with conn.cursor() as cur:
                cur.execute("SELECT fencing_token FROM jobs WHERE id=%s::uuid", (job_id,))
                token = cur.fetchone()[0]
                try:
                    cur.execute("INSERT INTO ledger_entries (job_id,fencing_token,worker_id,written_at) VALUES (%s::uuid,%s,'worker-b',NOW())", (job_id, token))
                    conn.commit(); results["b"] = "committed"
                except (psycopg2.errors.UniqueViolation,):
                    conn.rollback(); results["b"] = "unique_blocked"
        except psycopg2.OperationalError: results["b"] = "fault_error"
        except Exception as e: results["b"] = f"error:{e}"

    ta = threading.Thread(target=worker_a)
    tb = threading.Thread(target=worker_b)
    ta.start(); tb.start(); ta.join(timeout=5); tb.join(timeout=5)
    return ledger_count(job_id)

def test_correctness_at_0pct_fault_rate():
    dupes = sum(1 for i in range(100) if _race(seed(f"fi0_{i}_{uuid.uuid4().hex[:4]}"), FAULT_CLEAN) > 1)
    assert dupes == 0, f"{dupes} duplicates at 0% fault rate"

def test_correctness_at_5pct_fault_rate():
    dupes = sum(1 for i in range(100) if _race(seed(f"fi5_{i}_{uuid.uuid4().hex[:4]}"), FAULT_LOW) > 1)
    assert dupes == 0, f"{dupes} duplicates at 5% fault rate"

def test_correctness_at_10pct_fault_rate():
    dupes = sum(1 for i in range(100) if _race(seed(f"fi10_{i}_{uuid.uuid4().hex[:4]}"), FAULT_MEDIUM) > 1)
    assert dupes == 0, f"{dupes} duplicates at 10% fault rate"

def test_faults_surface_as_operational_error():
    config = FaultConfig(drop_rate=1.0, seed=0)
    conn = FaultProxy.connect(DATABASE_URL, config)
    raised = False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    except psycopg2.OperationalError as e:
        raised = True
        assert "fault_proxy" in str(e)
    conn.close()
    assert raised
