from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LeaseRecord:
    job_id: str
    payload: dict[str, Any]
    state: str = "queued"
    lease_owner: str | None = None
    fencing_token: int = 0
    retry_count: int = 0
    result: dict[str, Any] | None = None
    last_error: str | None = None


@dataclass
class LeaseTableSimulator:
    jobs: dict[str, LeaseRecord] = field(default_factory=dict)
    idempotency_index: dict[str, str] = field(default_factory=dict)

    def enqueue(self, job_id: str, payload: dict[str, Any], idempotency_key: str) -> LeaseRecord:
        if idempotency_key in self.idempotency_index:
            return self.jobs[self.idempotency_index[idempotency_key]]

        record = LeaseRecord(job_id=job_id, payload=payload)
        self.jobs[job_id] = record
        self.idempotency_index[idempotency_key] = job_id
        return record

    def claim(self, worker_id: str) -> tuple[str, int] | None:
        for record in self.jobs.values():
            if record.state in {"queued", "retry"}:
                record.state = "running"
                record.lease_owner = worker_id
                record.fencing_token += 1
                return record.job_id, record.fencing_token
        return None

    def takeover(self, job_id: str, worker_id: str) -> tuple[str, int]:
        record = self.jobs[job_id]
        record.state = "running"
        record.lease_owner = worker_id
        record.fencing_token += 1
        return record.job_id, record.fencing_token

    def complete(
        self,
        job_id: str,
        worker_id: str,
        submitted_fencing_token: int,
        result: dict[str, Any],
    ) -> bool:
        record = self.jobs[job_id]

        if record.lease_owner != worker_id:
            return False

        if record.fencing_token != submitted_fencing_token:
            return False

        if record.state == "succeeded":
            return False

        record.state = "succeeded"
        record.result = result
        return True

    def fail_retryable(self, job_id: str, error: str) -> None:
        record = self.jobs[job_id]
        record.retry_count += 1
        record.last_error = error
        record.state = "retry"
        record.lease_owner = None
