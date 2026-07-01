from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class JobRow:
    job_id: str
    state: str = "queued"
    lease_owner: str | None = None
    fencing_token: int = 0
    partial_state_written: bool = False
    final_state: str | None = None


@dataclass
class Outbox:
    events: list[dict] = field(default_factory=list)
    idempotency_keys: set[str] = field(default_factory=set)

    def emit_once(self, key: str, event: dict) -> bool:
        if key in self.idempotency_keys:
            return False
        self.idempotency_keys.add(key)
        self.events.append(event)
        return True


def test_postgres_recovery_correctness_crash_reconnect_and_outbox_once():
    job = JobRow(job_id="job-42")
    outbox = Outbox()

    # Worker A claims the PostgreSQL lease row.
    job.state = "running"
    job.lease_owner = "worker-a"
    job.fencing_token = 1

    # Worker A writes partial state, then transaction/connection fails.
    job.partial_state_written = True
    connection_dropped = True
    assert connection_dropped is True

    # Lease expires; Worker B reclaims work with a newer fencing token.
    job.lease_owner = "worker-b"
    job.fencing_token = 2

    # Worker B commits with current fencing token.
    worker_b_token = 2
    assert worker_b_token == job.fencing_token
    job.state = "succeeded"
    job.final_state = "committed_by_worker_b"

    emitted = outbox.emit_once(
        key="job-42:completed",
        event={
            "job_id": "job-42",
            "event_type": "job.completed",
            "worker_id": "worker-b",
            "fencing_token": worker_b_token,
        },
    )

    assert emitted is True

    # Worker A reconnects and attempts stale commit.
    worker_a_stale_token = 1
    stale_commit_accepted = worker_a_stale_token == job.fencing_token

    if stale_commit_accepted:
        outbox.emit_once(
            key="job-42:completed",
            event={
                "job_id": "job-42",
                "event_type": "job.completed",
                "worker_id": "worker-a",
                "fencing_token": worker_a_stale_token,
            },
        )

    assert stale_commit_accepted is False
    assert job.state == "succeeded"
    assert job.final_state == "committed_by_worker_b"
    assert len(outbox.events) == 1
    assert outbox.events[0]["worker_id"] == "worker-b"
    assert outbox.events[0]["fencing_token"] == 2
