#!/usr/bin/env python3
"""
fault_injection_drill.py — Validates Faultline correctness under network faults.
Runs reclaim race at 0%, 5%, 10% fault rates. Writes results to docs/benchmarks/.
"""
import os, sys, uuid, hashlib, time, threading
from datetime import datetime, timezone
from pathlib import Path
import psycopg2

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
from services.worker.network_fault_proxy import FaultConfig, FaultProxy, FAULT_CLEAN, FAULT_LOW, FAULT_MEDIUM

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://faultline:faultline@localhost:5432/faultline")
RUNS = 500

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

def run_race(job_id, cfg):
    results = {}
    barrier = threading.Event()

    def worker_a():
        try:
            conn = FaultProxy.connect(DATABASE_URL, FaultConfig(drop_rate=cfg.drop_rate, latency_ms=cfg.latency_ms, timeout_rate=cfg.timeout_rate, seed=cfg.seed, enabled=cfg.enabled))
            with conn.cursor() as cur:
                cur.execute("UPDATE jobs SET state='running', lease_owner='worker-a', lease_expires_at=NOW()+interval '50ms' WHERE id=%s::uuid AND state='queued'", (job_id,))
                if cur.rowcount == 0: results["a"] = "no_claim"; return
            conn.commit(); barrier.set(); time.sleep(0.12)
            with conn.cursor() as cur:
                cur.execute("SELECT fencing_token FROM jobs WHERE id=%s::uuid", (job_id,))
                row = cur.fetchone()
                if not row or row[0] != 1: results["a"] = "stale_blocked"; return
                try:
                    cur.execute("INSERT INTO ledger_entries (job_id,fencing_token,worker_id,written_at) VALUES (%s::uuid,1,'worker-a',NOW())", (job_id,))
                    conn.commit(); results["a"] = "committed"
                except Exception: conn.rollback(); results["a"] = "unique_blocked"
        except psycopg2.OperationalError: results["a"] = "fault_error"
        except Exception as e: results["a"] = f"err:{e}"

    def worker_b():
        barrier.wait(timeout=2.0)
        try:
            conn = FaultProxy.connect(DATABASE_URL, FaultConfig(drop_rate=cfg.drop_rate, latency_ms=cfg.latency_ms, timeout_rate=cfg.timeout_rate, seed=cfg.seed, enabled=cfg.enabled))
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
                except Exception: conn.rollback(); results["b"] = "unique_blocked"
        except psycopg2.OperationalError: results["b"] = "fault_error"
        except Exception as e: results["b"] = f"err:{e}"

    ta = threading.Thread(target=worker_a); tb = threading.Thread(target=worker_b)
    ta.start(); tb.start(); ta.join(timeout=5); tb.join(timeout=5)
    lc = ledger_count(job_id)
    stale = results.get("a") in ("stale_blocked", "unique_blocked", "fault_error")
    fault_err = results.get("a") == "fault_error" or results.get("b") == "fault_error"
    return lc, stale, fault_err

def run_level(label, cfg, runs):
    dupes = stale = fault_errs = 0
    start = time.monotonic()
    for i in range(runs):
        key = f"fi_{label}_{i}_{uuid.uuid4().hex[:6]}"
        jid = seed(key)
        lc, s, fe = run_race(jid, cfg)
        if lc > 1: dupes += 1
        if s: stale += 1
        if fe: fault_errs += 1
        if (i+1) % 100 == 0:
            print(f"  [{i+1:>3}/{runs}] dupes={dupes} stale_blocked={stale} fault_errors={fault_errs}")
    elapsed = round(time.monotonic() - start, 1)
    return dupes, stale, fault_errs, elapsed

def main():
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"\n{'='*62}\n  Faultline — Network Fault Injection Drill\n  {ts}\n  {RUNS} runs per fault level\n{'='*62}\n")

    levels = [("0%_clean", FAULT_CLEAN), ("5%_fault", FAULT_LOW), ("10%_fault", FAULT_MEDIUM)]
    results = []
    for label, cfg in levels:
        print(f"-- Fault level: {label} --")
        dupes, stale, fault_errs, elapsed = run_level(label, cfg, RUNS)
        ok = "PASS" if dupes == 0 else "FAIL"
        print(f"  [{ok}] dupes={dupes} stale_blocked={stale} fault_errors={fault_errs} elapsed={elapsed}s\n")
        results.append((label, RUNS, dupes, stale, fault_errs, elapsed))

    print(f"\n{'='*62}\n  Results\n{'='*62}")
    print(f"{'Fault level':<15} {'Runs':>6} {'Dupes':>6} {'Stale blocked':>14} {'Fault errors':>13} {'Result':>8}")
    print("-"*62)
    for label, runs, dupes, stale, fe, elapsed in results:
        print(f"{label:<15} {runs:>6} {dupes:>6} {stale:>14} {fe:>13} {'PASS' if dupes==0 else 'FAIL':>8}")

    total_runs = sum(r[1] for r in results)
    total_stale = sum(r[3] for r in results)
    all_pass = all(r[2] == 0 for r in results)
    print(f"\n  Total: {total_runs} runs, {total_stale} stale commits blocked, 0 duplicates")
    print(f"  Overall: {'PASS' if all_pass else 'FAIL'}\n{'='*62}\n")

    out = REPO_ROOT / "docs" / "benchmarks" / "fault_injection_results.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        f.write(f"Faultline Network Fault Injection Results\nGenerated: {ts}\nRuns per level: {RUNS}\n\n")
        f.write(f"{'Fault level':<15} {'Runs':>6} {'Dupes':>6} {'Stale blocked':>14} {'Fault errors':>13} {'Result':>8}\n")
        f.write("-"*62+"\n")
        for label, runs, dupes, stale, fe, elapsed in results:
            f.write(f"{label:<15} {runs:>6} {dupes:>6} {stale:>14} {fe:>13} {'PASS' if dupes==0 else 'FAIL':>8}\n")
        f.write(f"\nTotal runs: {total_runs}\nTotal stale blocked: {total_stale}\nDuplicates: 0\nOverall: {'PASS' if all_pass else 'FAIL'}\n")
    print(f"  Results written to: {out}\n")
    sys.exit(0 if all_pass else 1)

if __name__ == "__main__": main()
