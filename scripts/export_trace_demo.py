from tracing.otel_trace import new_trace_id, trace_event, to_jsonl
from pathlib import Path

trace_id = new_trace_id()

events = [
    trace_event(trace_id=trace_id, phase="claim_job", job_id="job-1", worker_id="worker-a", lease_epoch=1, fencing_token=1),
    trace_event(trace_id=trace_id, phase="acquire_lease", job_id="job-1", worker_id="worker-a", lease_epoch=1, fencing_token=1),
    trace_event(trace_id=trace_id, phase="lease_takeover", job_id="job-1", worker_id="worker-b", lease_epoch=2, fencing_token=2),
    trace_event(trace_id=trace_id, phase="commit_result", job_id="job-1", worker_id="worker-b", lease_epoch=2, fencing_token=2),
    trace_event(trace_id=trace_id, phase="reject_stale_write", job_id="job-1", worker_id="worker-a", lease_epoch=1, fencing_token=1),
]

Path("docs/dashboard").mkdir(parents=True, exist_ok=True)
Path("docs/dashboard/sample_trace.jsonl").write_text(to_jsonl(events))

print("wrote docs/dashboard/sample_trace.jsonl")
