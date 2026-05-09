from __future__ import annotations

import orjson
from pathlib import Path
from tracing.otel_trace import new_trace_id, trace_event

trace_id = new_trace_id()

events = [
    trace_event(
        trace_id=trace_id,
        phase="claim_job",
        job_id="job-1",
        worker_id="worker-a",
        lease_epoch=1,
        fencing_token=1,
    ),
    trace_event(
        trace_id=trace_id,
        phase="reject_stale_write",
        job_id="job-1",
        worker_id="worker-a",
        lease_epoch=1,
        fencing_token=1,
    ),
]

payload = [
    {
        "trace_id": e.trace_id,
        "name": e.phase,
        "attributes": {
            "job_id": e.job_id,
            "worker_id": e.worker_id,
            "lease_epoch": e.lease_epoch,
            "fencing_token": e.fencing_token,
        },
        "timestamp": e.timestamp,
    }
    for e in events
]

Path("docs/dashboard/otel_trace_export.json").write_bytes(
    orjson.dumps(payload, option=orjson.OPT_INDENT_2)
)

print("wrote docs/dashboard/otel_trace_export.json")
