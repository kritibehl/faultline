from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone


@dataclass(slots=True)
class FaultlineTraceEvent:
    trace_id: str
    phase: str
    job_id: str
    worker_id: str
    lease_epoch: int
    fencing_token: int
    timestamp: str


def new_trace_id() -> str:
    return uuid.uuid4().hex


def trace_event(
    *,
    trace_id: str,
    phase: str,
    job_id: str,
    worker_id: str,
    lease_epoch: int,
    fencing_token: int,
) -> FaultlineTraceEvent:
    return FaultlineTraceEvent(
        trace_id=trace_id,
        phase=phase,
        job_id=job_id,
        worker_id=worker_id,
        lease_epoch=lease_epoch,
        fencing_token=fencing_token,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def to_jsonl(events: list[FaultlineTraceEvent]) -> str:
    return "\n".join(json.dumps(asdict(e)) for e in events) + "\n"
