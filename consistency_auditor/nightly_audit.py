from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class JobRecord:
    job_id: str
    state: str


@dataclass
class EventRecord:
    event_id: str
    job_id: str
    event_type: str


@dataclass
class OutboxRecord:
    outbox_id: str
    job_id: str
    idempotency_key: str


@dataclass
class ConsistencyAuditResult:
    orphan_events: list[str] = field(default_factory=list)
    orphan_outbox_events: list[str] = field(default_factory=list)
    duplicate_outbox_keys: list[str] = field(default_factory=list)
    inconsistent_completed_jobs: list[str] = field(default_factory=list)

    @property
    def total_findings(self) -> int:
        return (
            len(self.orphan_events)
            + len(self.orphan_outbox_events)
            + len(self.duplicate_outbox_keys)
            + len(self.inconsistent_completed_jobs)
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "orphan_events": self.orphan_events,
            "orphan_outbox_events": self.orphan_outbox_events,
            "duplicate_outbox_keys": self.duplicate_outbox_keys,
            "inconsistent_completed_jobs": self.inconsistent_completed_jobs,
            "total_findings": self.total_findings,
        }


def run_nightly_audit(
    jobs: list[JobRecord],
    events: list[EventRecord],
    outbox: list[OutboxRecord],
) -> ConsistencyAuditResult:
    result = ConsistencyAuditResult()

    job_ids = {job.job_id for job in jobs}
    completed_jobs = {job.job_id for job in jobs if job.state == "succeeded"}
    completion_events = {
        event.job_id for event in events if event.event_type == "job.completed"
    }

    for event in events:
        if event.job_id not in job_ids:
            result.orphan_events.append(event.event_id)

    for record in outbox:
        if record.job_id not in job_ids:
            result.orphan_outbox_events.append(record.outbox_id)

    seen_keys: set[str] = set()
    for record in outbox:
        if record.idempotency_key in seen_keys:
            result.duplicate_outbox_keys.append(record.idempotency_key)
        seen_keys.add(record.idempotency_key)

    for job_id in completed_jobs:
        if job_id not in completion_events:
            result.inconsistent_completed_jobs.append(job_id)

    return result


def demo_clean_audit() -> dict[str, object]:
    jobs = [
        JobRecord("job-1", "succeeded"),
        JobRecord("job-2", "queued"),
        JobRecord("job-3", "succeeded"),
    ]
    events = [
        EventRecord("evt-1", "job-1", "job.completed"),
        EventRecord("evt-2", "job-3", "job.completed"),
    ]
    outbox = [
        OutboxRecord("out-1", "job-1", "idem-1"),
        OutboxRecord("out-2", "job-3", "idem-3"),
    ]

    return run_nightly_audit(jobs, events, outbox).to_dict()


def demo_dirty_audit() -> dict[str, object]:
    jobs = [
        JobRecord("job-1", "succeeded"),
        JobRecord("job-2", "succeeded"),
    ]
    events = [
        EventRecord("evt-1", "job-1", "job.completed"),
        EventRecord("evt-orphan", "job-missing", "job.completed"),
    ]
    outbox = [
        OutboxRecord("out-1", "job-1", "idem-1"),
        OutboxRecord("out-duplicate", "job-2", "idem-1"),
        OutboxRecord("out-orphan", "job-missing", "idem-missing"),
    ]

    return run_nightly_audit(jobs, events, outbox).to_dict()


if __name__ == "__main__":
    print({
        "clean_audit": demo_clean_audit(),
        "dirty_audit": demo_dirty_audit(),
    })
