from __future__ import annotations

import json
from pathlib import Path


INCIDENT = {
    "incident_id": "faultline-inc-001",
    "failure": "stale_worker_late_commit",
    "events": [
        {
            "time": "T+00s",
            "service": "worker-a",
            "event": "claim_job",
            "detail": "worker-a claimed job-1 with token=1"
        },
        {
            "time": "T+08s",
            "service": "worker-a",
            "event": "worker_stall",
            "detail": "worker heartbeat stopped"
        },
        {
            "time": "T+15s",
            "service": "queue_runtime",
            "event": "lease_expired",
            "detail": "job-1 eligible for takeover"
        },
        {
            "time": "T+17s",
            "service": "worker-b",
            "event": "lease_takeover",
            "detail": "worker-b advanced token to 2"
        },
        {
            "time": "T+22s",
            "service": "postgres",
            "event": "commit_accepted",
            "detail": "worker-b committed with token=2"
        },
        {
            "time": "T+29s",
            "service": "postgres",
            "event": "stale_commit_rejected",
            "detail": "worker-a late commit rejected with token=1"
        }
    ],
    "root_cause": "worker resumed after lease ownership advanced",
    "recovery": [
        "accepted current-owner commit",
        "rejected stale-worker write",
        "preserved replay artifact",
        "operator reviewed duplicate-risk panel"
    ],
    "final_state": "consistent"
}


def reconstruct() -> dict[str, object]:
    out = Path("incident_timeline")
    out.mkdir(parents=True, exist_ok=True)
    (out / "incident_timeline.json").write_text(json.dumps(INCIDENT, indent=2))
    return INCIDENT


if __name__ == "__main__":
    print(json.dumps(reconstruct(), indent=2))
