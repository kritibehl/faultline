import json
from collections import Counter, defaultdict
from pathlib import Path


def load_race_artifacts(root="artifacts/races"):
    root_path = Path(root)
    if not root_path.exists():
        return []
    out = []
    for path in sorted(root_path.glob("*.json")):
        try:
            out.append(json.loads(path.read_text()))
        except Exception:
            continue
    return out


def summarize_logs(text: str):
    counters = Counter()
    events = []
    for line in text.splitlines():
        low = line.lower()

        if "claim" in low:
            counters["claim"] += 1
            events.append(("claim", line))
        if "lease" in low:
            counters["lease"] += 1
            events.append(("lease", line))
        if "token" in low or "fenc" in low:
            counters["token"] += 1
            events.append(("token", line))
        if "fault" in low or "inject" in low or "timeout" in low or "drop" in low:
            counters["fault_injected"] += 1
            events.append(("fault_injected", line))
        if "retry" in low:
            counters["retry_triggered"] += 1
            events.append(("retry_triggered", line))
        if "stale" in low or "reject" in low:
            counters["stale_write_blocked"] += 1
            events.append(("stale_write_blocked", line))
        if "commit" in low and ("accept" in low or "succeed" in low):
            counters["commit_accepted"] += 1
            events.append(("commit_accepted", line))
        elif "commit" in low:
            counters["commit_attempt"] += 1
            events.append(("commit_attempt", line))

    return counters, events


def build_race_report(artifact: dict):
    worker_a = artifact.get("worker_a_log", "")
    worker_b = artifact.get("worker_b_log", "")
    final_state = artifact.get("final_state", {})

    a_counts, a_events = summarize_logs(worker_a)
    b_counts, b_events = summarize_logs(worker_b)

    token_history = []
    if final_state.get("fencing_token") is not None:
        token_history.append(final_state["fencing_token"])

    claim_winner = None
    if final_state.get("lease_owner") == "worker-a":
        claim_winner = "worker-a"
    elif final_state.get("lease_owner") == "worker-b":
        claim_winner = "worker-b"

    report = {
        "job_id": artifact.get("job_id"),
        "claim_winner": claim_winner,
        "token_history": token_history,
        "db_state_transitions": [final_state],
        "worker_event_order": {
            "worker-a": [{"kind": k, "line": line} for k, line in a_events],
            "worker-b": [{"kind": k, "line": line} for k, line in b_events],
        },
        "counters": {
            "worker-a": dict(a_counts),
            "worker-b": dict(b_counts),
        },
        "final_state": final_state,
    }
    return report


def explain_report(report: dict):
    evidence = []
    cause = "unknown"
    confidence = "low"
    blocked = []

    a = report["counters"].get("worker-a", {})
    b = report["counters"].get("worker-b", {})
    final_state = report.get("final_state", {})

    if a.get("stale_write_blocked", 0) > 0:
        cause = "stale worker attempted commit after losing lease"
        confidence = "high"
        evidence.append("worker-a log contains stale/reject/fencing evidence")
        blocked.append("duplicate or stale commit acceptance")

    if final_state.get("fencing_token", 0) >= 2:
        evidence.append("fencing token advanced beyond first claim")
        if confidence == "low":
            confidence = "medium"

    if final_state.get("state") == "succeeded":
        evidence.append("job reached terminal succeeded state")
        blocked.append("user-visible failed completion after reclaim")

    if b.get("claim", 0) > 0:
        evidence.append("worker-b log contains claim path evidence")

    return {
        "likely_cause": cause,
        "evidence": evidence,
        "confidence": confidence,
        "blocked_failure_mode": blocked,
    }


def dashboard_summary(artifacts: list[dict]):
    totals = Counter()
    per_job = []
    for artifact in artifacts:
        report = build_race_report(artifact)
        explanation = explain_report(report)
        fs = report.get("final_state", {})
        stale = report["counters"].get("worker-a", {}).get("stale_write_blocked", 0) + \
                report["counters"].get("worker-b", {}).get("stale_write_blocked", 0)

        item = {
            "job_id": artifact.get("job_id"),
            "status": fs.get("state"),
            "lease_owner": fs.get("lease_owner"),
            "fencing_token": fs.get("fencing_token"),
            "attempts": fs.get("attempts"),
            "stale_write_rejections": stale,
            "likely_cause": explanation["likely_cause"],
            "confidence": explanation["confidence"],
        }
        per_job.append(item)
        totals["jobs"] += 1
        if fs.get("state") == "succeeded":
            totals["succeeded"] += 1
        else:
            totals["failed_or_other"] += 1
        totals["stale_write_rejections"] += stale

    return {
        "totals": dict(totals),
        "jobs": per_job,
    }
