#!/usr/bin/env python3
"""
Faultline scenario runner CLI.
Usage: python3 services/cli/scenario_runner.py <scenario> [--report]
Scenarios: lease-expiry worker-crash reclaim-race retry-backoff max-retries all
"""
import argparse, hashlib, json, os, subprocess, sys, time, uuid, threading
from datetime import datetime, timezone
from pathlib import Path
import psycopg2

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://faultline:faultline@localhost:5432/faultline")
WORKER_CMD = [sys.executable, str(REPO_ROOT / "services/worker/worker.py")]
REPORTS_DIR = REPO_ROOT / "docs" / "reports"

def _db(): return psycopg2.connect(DATABASE_URL)
def _hash(): return hashlib.sha256(b"{}").hexdigest()

def _seed(key, max_attempts=3):
    job_id = str(uuid.uuid4())
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ledger_entries WHERE job_id IN (SELECT id FROM jobs WHERE idempotency_key=%s)", (key,))
            cur.execute("DELETE FROM jobs WHERE idempotency_key=%s", (key,))
            cur.execute(
                "INSERT INTO jobs (id,payload,payload_hash,state,attempts,max_attempts,idempotency_key,next_run_at) "
                "VALUES (%s,'{}' ,%s,'queued',0,%s,%s,NOW())",
                (job_id, _hash(), max_attempts, key)
            )
        conn.commit()
    return job_id

def _run(job_id, extra_env, timeout=30):
    """Run worker pinned to a specific job_id via CLAIM_JOB_ID."""
    env = {
        **os.environ,
        "DATABASE_URL": DATABASE_URL,
        "METRICS_ENABLED": "0",
        "PYTHONPATH": str(REPO_ROOT),
        "CLAIM_JOB_ID": job_id,
        **extra_env,
    }
    log = f"/tmp/fl_{job_id[:8]}.log"
    p = subprocess.Popen(WORKER_CMD, env=env, stdout=open(log,"w"), stderr=subprocess.STDOUT)
    try: p.wait(timeout=timeout)
    except subprocess.TimeoutExpired: p.kill(); p.wait()
    return open(log).read()

def _job(job_id):
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT state,fencing_token,attempts,last_error,next_run_at FROM jobs WHERE id=%s",(job_id,))
            return cur.fetchone()

def _ledger(job_id):
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM ledger_entries WHERE job_id=%s",(job_id,))
            return cur.fetchone()[0]

def _clear_barrier(name):
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM barriers WHERE name=%s",(name,))
        conn.commit()

class R:
    def __init__(self, name):
        self.name=name; self.checks=[]; self.passed=0; self.failed=0; self.start=time.monotonic()
    def check(self, label, ok, detail=""):
        self.checks.append({"label":label,"status":"PASS" if ok else "FAIL","detail":detail})
        if ok: self.passed+=1; print(f"  PASS: {label}")
        else:  self.failed+=1; print(f"  FAIL: {label}" + (f" ({detail})" if detail else ""))
    def summary(self):
        elapsed=time.monotonic()-self.start
        status="PASS" if self.failed==0 else "FAIL"
        print(f"\n  [{status}] {self.name} — {self.passed}/{self.passed+self.failed} checks ({elapsed:.1f}s)")
        return self.failed==0
    def to_dict(self):
        return {"scenario":self.name,"passed":self.passed,"failed":self.failed,"checks":self.checks,"duration_s":round(time.monotonic()-self.start,2)}

def scenario_lease_expiry():
    r=R("lease-expiry"); print("\n-- lease-expiry: worker sleeps past TTL, successor reclaims --")
    job_id=_seed("sc_lease_expiry")
    # A: 1s lease, sleeps 2.5s → expires
    _run(job_id,{"LEASE_SECONDS":"1","WORK_SLEEP_SECONDS":"2.5","EXIT_ON_STALE":"1","MAX_LOOPS":"5"})
    # B: reclaims expired job
    _run(job_id,{"LEASE_SECONDS":"30","WORK_SLEEP_SECONDS":"0","EXIT_ON_SUCCESS":"1","MAX_LOOPS":"10"})
    state,token,_,_,_=_job(job_id); ledger=_ledger(job_id)
    r.check("job succeeded",state=="succeeded",f"state={state}")
    r.check("exactly 1 ledger entry",ledger==1,f"ledger={ledger}")
    r.summary(); return r

def scenario_worker_crash():
    r=R("worker-crash"); print("\n-- worker-crash: crash before commit, successor recovers --")
    job_id=_seed("sc_worker_crash")
    log_a=_run(job_id,{"CRASH_AT":"before_commit","LEASE_SECONDS":"2","MAX_LOOPS":"5","WORK_SLEEP_SECONDS":"0"})
    time.sleep(3)  # let lease expire
    _run(job_id,{"LEASE_SECONDS":"30","EXIT_ON_SUCCESS":"1","MAX_LOOPS":"20","WORK_SLEEP_SECONDS":"0"})
    state,token,_,_,_=_job(job_id); ledger=_ledger(job_id)
    r.check("crash injected","crash_injected" in log_a)
    r.check("job succeeded",state=="succeeded",f"state={state}")
    r.check("exactly 1 ledger entry",ledger==1,f"ledger={ledger}")
    r.summary(); return r

def scenario_reclaim_race():
    r=R("reclaim-race"); print("\n-- reclaim-race: concurrent workers, exactly one commits --")
    _clear_barrier("sc_reclaim")
    job_id=_seed("sc_reclaim_race")
    logs={}
    def run_a():
        logs["a"]=_run(job_id,{
            "LEASE_SECONDS":"1","WORK_SLEEP_SECONDS":"2.5",
            "EXIT_ON_STALE":"1","BARRIER_OPEN":"sc_reclaim","MAX_LOOPS":"10"
        })
    def run_b():
        logs["b"]=_run(job_id,{
            "LEASE_SECONDS":"30","WORK_SLEEP_SECONDS":"0",
            "EXIT_ON_SUCCESS":"1","BARRIER_WAIT":"sc_reclaim",
            "BARRIER_TIMEOUT_S":"10","MAX_LOOPS":"10"
        })
    ta=threading.Thread(target=run_a); tb=threading.Thread(target=run_b)
    ta.start(); tb.start(); ta.join(timeout=25); tb.join(timeout=25)
    state,token,_,_,_=_job(job_id); ledger=_ledger(job_id)
    r.check("job succeeded",state=="succeeded",f"state={state}")
    r.check("exactly 1 ledger entry",ledger==1,f"ledger={ledger}")
    r.summary(); return r

def scenario_retry_backoff():
    r=R("retry-backoff"); print("\n-- retry-backoff: failure triggers backoff, succeeds on retry --")
    job_id=_seed("sc_retry_backoff2",max_attempts=3)
    # Fail on attempt 0
    _run(job_id,{"SIMULATE_FAILURE":"1","LEASE_SECONDS":"30","MAX_LOOPS":"1","WORK_SLEEP_SECONDS":"0"})
    state,_,attempts,last_error,next_run_at=_job(job_id)
    r.check("re-queued after failure",state=="queued",f"state={state}")
    r.check("attempts incremented",attempts==1,f"attempts={attempts}")
    r.check("next_run_at set (backoff active)",next_run_at is not None)
    # Fast-forward and succeed
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE jobs SET next_run_at=NOW()-interval '1s' WHERE id=%s",(job_id,))
        conn.commit()
    _run(job_id,{"LEASE_SECONDS":"30","EXIT_ON_SUCCESS":"1","MAX_LOOPS":"10","WORK_SLEEP_SECONDS":"0"})
    state2,_,attempts2,_,_=_job(job_id); ledger=_ledger(job_id)
    r.check("succeeded on retry",state2=="succeeded",f"state={state2}")
    r.check("1 ledger entry",ledger==1,f"ledger={ledger}")
    r.summary(); return r

def scenario_max_retries():
    r=R("max-retries"); print("\n-- max-retries: exhausts attempts, state=failed --")
    job_id=_seed("sc_max_retries2",max_attempts=1)
    _run(job_id,{"SIMULATE_FAILURE":"1","LEASE_SECONDS":"30","MAX_LOOPS":"10","WORK_SLEEP_SECONDS":"0"})
    state,_,attempts,last_error,next_run_at=_job(job_id)
    r.check("state=failed",state=="failed",f"state={state}")
    r.check("attempts=1",attempts==1,f"attempts={attempts}")
    r.check("error recorded",last_error is not None,f"last_error={last_error}")
    r.summary(); return r

SCENARIOS = {
    "lease-expiry":scenario_lease_expiry,
    "worker-crash":scenario_worker_crash,
    "reclaim-race":scenario_reclaim_race,
    "retry-backoff":scenario_retry_backoff,
    "max-retries":scenario_max_retries,
}

def write_report(results, path):
    ts=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    passed=sum(1 for r in results if r.failed==0); total=len(results)
    rows=""
    for r in results:
        status="PASS" if r.failed==0 else "FAIL"; color="#2ecc71" if r.failed==0 else "#e74c3c"
        checks="".join(
            f'<li style="color:{"#2ecc71" if c["status"]=="PASS" else "#e74c3c"}">'
            f'{c["status"]}: {c["label"]}'
            + (f' — {c["detail"]}' if c.get("detail") and c["status"]=="FAIL" else "")
            + "</li>"
            for c in r.checks
        )
        rows+=f'<tr><td><b>{r.name}</b></td><td style="color:{color};font-weight:bold">{status}</td><td>{r.passed}/{r.passed+r.failed}</td><td><ul style="margin:0;padding-left:1em">{checks}</ul></td></tr>'
    pass_color="#2ecc71" if passed==total else "#e74c3c"
    html=f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Faultline Scenarios {ts}</title>
<style>body{{font-family:monospace;background:#0d1117;color:#c9d1d9;padding:2rem;max-width:1100px;margin:0 auto}}
h1{{color:#58a6ff}}table{{width:100%;border-collapse:collapse}}
th{{background:#161b22;color:#58a6ff;padding:.6rem 1rem;text-align:left;border-bottom:2px solid #30363d}}
td{{padding:.5rem 1rem;border-bottom:1px solid #21262d;vertical-align:top}}
tr:hover td{{background:#161b22}}ul{{font-size:.85rem;margin:0}}</style></head>
<body><h1>Faultline — Scenario Report</h1>
<p style="color:#8b949e">{ts} &nbsp;|&nbsp; <b style="color:{pass_color}">{passed}/{total} scenarios passed</b></p>
<table><thead><tr><th>Scenario</th><th>Status</th><th>Checks</th><th>Details</th></tr></thead>
<tbody>{rows}</tbody></table></body></html>'''
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(html)
    print(f"\n  Report: {path}")

def main():
    parser=argparse.ArgumentParser(prog="faultline scenario")
    parser.add_argument("scenario",choices=list(SCENARIOS.keys())+["all"])
    parser.add_argument("--report",action="store_true")
    args=parser.parse_args()
    global DATABASE_URL
    to_run=list(SCENARIOS.values()) if args.scenario=="all" else [SCENARIOS[args.scenario]]
    print("\n"+"="*60+"\n  Faultline Scenario Runner\n"+"="*60)
    results=[fn() for fn in to_run]
    passed=sum(1 for r in results if r.failed==0); total=len(results)
    print(f"\n{'='*60}\n  Results: {passed}/{total} scenarios passed\n{'='*60}")
    if args.report:
        ts=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        write_report(results, REPORTS_DIR/f"scenario_{ts}.html")
    sys.exit(0 if passed==total else 1)

if __name__=="__main__": main()
