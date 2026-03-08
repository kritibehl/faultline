#!/usr/bin/env python3
"""
Faultline Inspector — HTML job timeline report.
Usage: python3 services/inspector/report.py [--recent N] [--output FILE]
"""
import argparse, os, sys
from datetime import datetime, timezone
from pathlib import Path
import psycopg2

REPO_ROOT = Path(__file__).parent.parent.parent
DATABASE_URL = os.environ.get("DATABASE_URL","postgresql://faultline:faultline@localhost:5432/faultline")
REPORTS_DIR = REPO_ROOT / "docs" / "reports"
STATE_COLORS = {"queued":"#58a6ff","running":"#f0a500","succeeded":"#2ecc71","failed":"#e74c3c"}

def _db(): return psycopg2.connect(DATABASE_URL)

def fetch_jobs(limit=20):
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id,state,fencing_token,lease_owner,attempts,max_attempts,last_error,next_run_at,created_at,updated_at FROM jobs ORDER BY created_at DESC LIMIT %s",(limit,))
            cols=[d[0] for d in cur.description]
            return [dict(zip(cols,row)) for row in cur.fetchall()]

def fetch_ledger(job_ids):
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT job_id,fencing_token,created_at FROM ledger_entries WHERE job_id=ANY(%s::uuid[]) ORDER BY created_at",(job_ids,))
            index={}
            for row in cur.fetchall():
                index.setdefault(str(row[0]),[]).append(row)
            return index

def fetch_counts():
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT state,COUNT(*) FROM jobs GROUP BY state ORDER BY state")
            return dict(cur.fetchall())

def fmt(val):
    if val is None: return "<span style='color:#6e7681'>—</span>"
    if isinstance(val,datetime): return val.strftime("%H:%M:%S")
    return str(val)

def badge(state):
    c=STATE_COLORS.get(state,"#8b949e")
    return f'<span style="background:{c};color:#0d1117;padding:2px 8px;border-radius:4px;font-weight:bold;font-size:.8rem">{state}</span>'

def generate(jobs, ledger_index, counts):
    ts=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    summary="".join(f'<span style="margin-right:1.5rem"><span style="color:{STATE_COLORS.get(s,"#8b949e")};font-weight:bold">{c}</span> {s}</span>' for s,c in sorted(counts.items()))
    rows=""
    for job in jobs:
        jid=str(job["id"]); entries=ledger_index.get(jid,[])
        lc=len(entries)
        if lc==0: lcel='<span style="color:#6e7681">no entry</span>'
        elif lc==1: lcel=f'<span style="color:#2ecc71">1 entry (token={entries[0][1]})</span>'
        else: lcel=f'<span style="color:#e74c3c">{lc} entries — DUPLICATE</span>'
        err=f'<div style="color:#e74c3c;font-size:.8rem">{str(job["last_error"])[:100]}</div>' if job["last_error"] else ""
        rows+=f'<tr><td style="font-family:monospace;font-size:.85rem" title="{jid}">{jid[:8]}…</td><td>{badge(job["state"])}</td><td style="font-size:.85rem">token={job["fencing_token"]} retries={job["attempts"]}</td><td style="font-size:.8rem;color:#8b949e">{fmt(job["created_at"])}</td><td style="font-size:.85rem">{lcel}{err}</td><td style="font-size:.8rem;color:#8b949e">{str(job.get("lease_owner",""))[:16] if job.get("lease_owner") else "—"}</td></tr>'
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Faultline Inspector {ts}</title>
<style>*{{box-sizing:border-box}}body{{font-family:monospace;background:#0d1117;color:#c9d1d9;padding:2rem;max-width:1400px;margin:0 auto}}
h1{{color:#58a6ff;border-bottom:1px solid #30363d;padding-bottom:.5rem}}.sum{{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:1rem 1.5rem;margin-bottom:1.5rem}}
table{{width:100%;border-collapse:collapse}}th{{background:#161b22;color:#58a6ff;padding:.6rem 1rem;text-align:left;position:sticky;top:0}}
td{{padding:.5rem 1rem;border-bottom:1px solid #21262d;vertical-align:top}}tr:hover td{{background:#161b22}}</style></head>
<body><h1>Faultline Inspector</h1><p style="color:#6e7681">{ts} | {len(jobs)} jobs</p>
<div class="sum">{summary}</div>
<table><thead><tr><th>Job ID</th><th>State</th><th>Token/Retries</th><th>Created</th><th>Ledger</th><th>Lease Owner</th></tr></thead>
<tbody>{rows}</tbody></table></body></html>'''

def main():
    parser=argparse.ArgumentParser(prog="faultline inspect")
    parser.add_argument("--recent",type=int,default=20)
    parser.add_argument("--output")
    parser.add_argument("--db-url",default=DATABASE_URL)
    args=parser.parse_args()
    DATABASE_URL=args.db_url
    jobs=fetch_jobs(args.recent)
    if not jobs: print("No jobs found."); return
    ledger=fetch_ledger([str(j["id"]) for j in jobs])
    counts=fetch_counts()
    html=generate(jobs,ledger,counts)
    if args.output: out=Path(args.output)
    else:
        ts=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out=REPORTS_DIR/f"inspect_{ts}.html"
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(html)
    print(f"Report: {out}\nopen {out}")

if __name__=="__main__": main()
