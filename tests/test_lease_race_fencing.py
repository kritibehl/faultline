"""
tests/test_lease_race_fencing.py
─────────────────────────────────
Deterministic lease-expiry race reproduction harness.

Validates that the fencing token mechanism correctly prevents stale writes
under adversarial timing across TOTAL_RUNS controlled iterations.

Race Scenario (per run)
───────────────────────
    1. Worker A claims job             → fencing_token = N+1
    2. Worker A opens barrier          → signals B to start
    3. Worker A sleeps 1.2s            → lease (1s) expires during sleep
    4. Worker B waits on barrier       → barrier now open
    5. Worker B reclaims job           → fencing_token = N+2  (A's token is stale)
    6. Worker B executes + commits     → ledger entry (job_id, N+2) written
    7. Worker A wakes, assert_fence()  → stale_token / lease_expired detected → blocked
    8. Worker A exits with reason=stale

Invariants validated per run
─────────────────────────────
    ✓ Worker A emits stale_write_blocked
    ✓ Worker B exits with reason=success
    ✓ Job reaches state=succeeded
    ✓ Exactly 1 ledger entry (no duplicate side effects)
    ✓ fencing_token >= 2 (A incremented to N+1, B to N+2)
    ✓ MIN(fencing_token) == MAX(fencing_token) in ledger (one epoch only)

Results written to tests/results/lease_race_500_runs.txt after each run.
"""

import hashlib
import os
import subprocess
import sys
import time
import uuid

import psycopg2

WORKER_CMD = [sys.executable, "-m", "services.worker.worker"]
TOTAL_RUNS = int(os.environ.get("RACE_RUNS", "500"))
RESULTS_PATH = "tests/results/lease_race_500_runs.txt"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _payload_hash(payload_str: str) -> str:
    return hashlib.sha256(payload_str.encode()).hexdigest()


def _db(url: str):
    return psycopg2.connect(url)


def _ensure_barriers(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS barriers (
            name TEXT PRIMARY KEY,
            opened_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )


def _reset_barrier(cur, name: str):
    _ensure_barriers(cur)
    cur.execute("DELETE FROM barriers WHERE name=%s", (name,))


def _seed_job(cur, job_id: str):
    payload = "{}"
    cur.execute(
        """
        INSERT INTO jobs (
            id,
            payload,
            payload_hash,
            state,
            attempts,
            max_attempts,
            lease_owner,
            lease_expires_at,
            fencing_token,
            next_run_at
        )
        VALUES (%s, %s, %s, 'queued', 0, 5, NULL, NULL, 0, NOW())
        """,
        (job_id, payload, _payload_hash(payload)),
    )


def _wait_state(database_url: str, job_id: str, want: str, timeout_s: float = 10) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        with _db(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT state FROM jobs WHERE id=%s", (job_id,))
                row = cur.fetchone()
                if row and row[0] == want:
                    return True
        time.sleep(0.1)
    return False


def _ledger_info(database_url: str, job_id: str):
    with _db(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*), MIN(fencing_token), MAX(fencing_token)
                FROM ledger_entries WHERE job_id=%s
                """,
                (job_id,),
            )
            return cur.fetchone()  # (count, min_tok, max_tok)


def _job_debug(database_url: str, job_id: str) -> str:
    with _db(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT state, lease_owner, lease_expires_at, fencing_token
                FROM jobs
                WHERE id=%s
                """,
                (job_id,),
            )
            return str(cur.fetchone())


def _kill(p):
    if p is None:
        return
    try:
        if p.poll() is None:
            p.kill()
    except Exception:
        pass
    try:
        p.communicate(timeout=3)
    except Exception:
        pass


def _read_until(p: subprocess.Popen, needle: str, timeout_s: float) -> str:
    deadline = time.time() + timeout_s
    buf = []
    while time.time() < deadline:
        try:
            line = p.stdout.readline() if p.stdout else ""
        except Exception:
            line = ""
        if line:
            buf.append(line)
            if needle in line:
                break
        else:
            time.sleep(0.01)
    return "".join(buf)


# ─────────────────────────────────────────────────────────────────────────────
# Single-run race scenario
# ─────────────────────────────────────────────────────────────────────────────

def _run_once(database_url: str, run_number: int) -> dict:
    job_id = str(uuid.uuid4())
    barrier = "after_lease_acquire"

    with _db(database_url) as conn:
        with conn.cursor() as cur:
            # Make the harness deterministic by clearing prior state.
            cur.execute("DELETE FROM ledger_entries")
            cur.execute("DELETE FROM jobs")
            _reset_barrier(cur, barrier)
            _seed_job(cur, job_id)

            cur.execute(
                """
                SELECT state, lease_owner, lease_expires_at, fencing_token
                FROM jobs
                WHERE id=%s
                """,
                (job_id,),
            )
            seeded_state = cur.fetchone()

        conn.commit()

    base_env = os.environ.copy()
    base_env.update({
        "DATABASE_URL": database_url,
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": os.getcwd(),
        "BARRIER_TIMEOUT_S": "60",
        "METRICS_ENABLED": "0",
        "AUTOPSY_LOG_PATH": "docs/autopsy/assets/logs.jsonl",
    })

    env_a = base_env.copy()
    env_a.update({
        "WORKER_ID": "worker-a",
        "CLAIM_JOB_ID": job_id,
        "LEASE_SECONDS": "1",
        "FAULTLINE_SINGLE_RUN": "1",
        "BARRIER_OPEN": barrier,
        "WORK_SLEEP_SECONDS": "1.2",
        "MAX_LOOPS": "3000",
        "EXIT_ON_STALE": "1",
    })

    env_b = base_env.copy()
    env_b.update({
        "WORKER_ID": "worker-b",
        "CLAIM_JOB_ID": job_id,
        "LEASE_SECONDS": "30",
        "FAULTLINE_SINGLE_RUN": "0",
        "BARRIER_WAIT": barrier,
        "WORK_SLEEP_SECONDS": "0",
        "MAX_LOOPS": "6000",
        "EXIT_ON_SUCCESS": "1",
    })

    p_a = p_b = None
    out_a_pre = out_b_pre = out_a = out_b = ""

    try:
        p_a = subprocess.Popen(
            WORKER_CMD,
            env=env_a,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        out_a_claim = _read_until(p_a, '"event": "lease_acquired"', timeout_s=3)
        if '"event": "lease_acquired"' not in out_a_claim:
            _kill(p_a)
            return {
                "passed": False,
                "stale_blocked": False,
                "b_succeeded": False,
                "ledger_count": 0,
                "fencing_token": None,
                "error": (
                    f"Run {run_number}: Worker A never claimed job. "
                    f"Worker A output: {out_a_claim[:2000]!r}. "
                    f"Job state now: {_job_debug(database_url, job_id)}"
                ),
            }

        out_a_pre = out_a_claim + _read_until(p_a, '"event": "barrier_open"', timeout_s=5)
        if '"event": "barrier_open"' not in out_a_pre:
            _kill(p_a)
            return {
                "passed": False,
                "stale_blocked": False,
                "b_succeeded": False,
                "ledger_count": 0,
                "fencing_token": None,
                "error": (
                    f"Run {run_number}: Worker A never opened barrier. "
                    f"Worker A output: {out_a_pre[:2000]!r}. "
                    f"Job state now: {_job_debug(database_url, job_id)}"
                ),
            }

        time.sleep(0.2)

        p_b = subprocess.Popen(
            WORKER_CMD,
            env=env_b,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        out_b_pre = _read_until(p_b, '"reason": "success"', timeout_s=8)

        try:
            out_a, _ = p_a.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            _kill(p_a)
            out_a = ""

        try:
            out_b, _ = p_b.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            _kill(p_b)
            out_b = ""

    finally:
        _kill(p_a)
        _kill(p_b)

    full_a = out_a_pre + out_a
    full_b = out_b_pre + out_b

    stale_blocked = "stale_write_blocked" in full_a
    b_succeeded = '"reason": "success"' in full_b
    job_ok = _wait_state(database_url, job_id, "succeeded", timeout_s=10)
    count, min_tok, max_tok = _ledger_info(database_url, job_id)

    passed = (
        stale_blocked
        and b_succeeded
        and job_ok
        and count == 1
        and min_tok == max_tok
        and int(min_tok or 0) >= 2
    )

    parts = []
    if not stale_blocked:
        parts.append("stale write was not blocked")
    if not b_succeeded:
        parts.append("worker B did not succeed")
    if not job_ok:
        parts.append("job did not reach succeeded")
    if count != 1:
        parts.append(f"ledger_count={count}")
    if min_tok != max_tok:
        parts.append(f"min_tok={min_tok} max_tok={max_tok}")
    if int(min_tok or 0) < 2:
        parts.append(f"fencing token too low: {min_tok}")

    return {
        "passed": passed,
        "stale_blocked": stale_blocked,
        "b_succeeded": b_succeeded,
        "ledger_count": count,
        "fencing_token": max_tok,
        "error": None if passed else (
            f"Run {run_number}: " + ", ".join(parts) +
            f". Worker A output: {full_a[:1500]!r}. "
            f"Worker B output: {full_b[:1500]!r}. "
            f"Job state now: {_job_debug(database_url, job_id)}"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Harness
# ─────────────────────────────────────────────────────────────────────────────

def test_lease_expiry_race_is_blocked_by_fencing(database_url):
    os.makedirs("tests/results", exist_ok=True)
    os.makedirs("docs/autopsy/assets", exist_ok=True)

    passed = failed = duplicate_ledger = stale_count = 0
    errors = []

    with open(RESULTS_PATH, "w") as f:
        f.write("Faultline — lease-expiry race fencing validation\n")
        f.write(f"Runs: {TOTAL_RUNS}\n")
        f.write("=" * 60 + "\n\n")

        for run in range(1, TOTAL_RUNS + 1):
            r = _run_once(database_url, run)

            if r["stale_blocked"]:
                stale_count += 1
            if (r["ledger_count"] or 0) > 1:
                duplicate_ledger += 1

            if r["passed"]:
                passed += 1
                status = "PASS"
            else:
                failed += 1
                status = "FAIL"
                if r["error"]:
                    errors.append(r["error"])

            line = (
                f"=== Run {run:4d} === {status} | "
                f"stale_blocked={r['stale_blocked']} "
                f"b_succeeded={r['b_succeeded']} "
                f"ledger_entries={r['ledger_count']} "
                f"fencing_token={r.get('fencing_token')}"
            )
            if r["error"]:
                line += f"\n  ERROR: {r['error']}"
            f.write(line + "\n")
            f.flush()

            if run % 50 == 0 or run == TOTAL_RUNS:
                print(
                    f"  [{run:4d}/{TOTAL_RUNS}] "
                    f"passed={passed} failed={failed} "
                    f"stale_blocked={stale_count} "
                    f"duplicate_ledger={duplicate_ledger}",
                    flush=True,
                )

        summary_lines = [
            "",
            "=" * 60,
            "RESULTS",
            "=" * 60,
            f"Total runs            : {TOTAL_RUNS}",
            f"Passed                : {passed}",
            f"Failed                : {failed}",
            f"Stale writes blocked  : {stale_count}/{TOTAL_RUNS}",
            f"Duplicate ledger entries: {duplicate_ledger}",
        ]

        if errors:
            summary_lines += ["", "FAILURES:"] + [f"  {e}" for e in errors[:20]]

        verdict = (
            f"\n✅ ALL INVARIANTS HELD — 0 duplicate executions across {TOTAL_RUNS} controlled runs"
            if failed == 0
            else f"\n❌ {failed} FAILURE(S) DETECTED"
        )
        summary_lines.append(verdict)
        summary = "\n".join(summary_lines) + "\n"

        f.write(summary)
        print(summary)

    assert duplicate_ledger == 0, (
        f"Duplicate side effects in {duplicate_ledger}/{TOTAL_RUNS} runs. "
        f"See {RESULTS_PATH}"
    )
    assert failed == 0, (
        f"{failed}/{TOTAL_RUNS} runs failed. See {RESULTS_PATH}"
    )