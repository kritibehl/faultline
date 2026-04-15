from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Literal


Severity = Literal["low", "medium", "high", "critical"]


@dataclass(slots=True)
class FaultlineFailureSignal:
    failure_family: str
    severity: Severity
    safe_to_operate: bool
    evidence: dict
    recommended_action: str


def stale_worker_race_signal(
    *,
    job_id: str,
    stale_fencing_token: int,
    current_fencing_token: int,
    duplicate_commits_detected: int = 0,
) -> FaultlineFailureSignal:
    return FaultlineFailureSignal(
        failure_family="stale_worker_race",
        severity="high",
        safe_to_operate=(duplicate_commits_detected == 0),
        evidence={
            "job_id": job_id,
            "stale_fencing_token": stale_fencing_token,
            "current_fencing_token": current_fencing_token,
            "duplicate_commits_detected": duplicate_commits_detected,
        },
        recommended_action=(
            "investigate reclaim timing, lease sizing, and stale-worker protection boundaries"
        ),
    )


def to_json(signal: FaultlineFailureSignal) -> str:
    return json.dumps(asdict(signal), indent=2)
