from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


RetryMode = Literal["exponential", "fixed", "none"]
JobState = Literal["queued", "running", "succeeded", "failed"]


@dataclass(slots=True)
class RetryPolicy:
    mode: RetryMode = "exponential"
    max_attempts: int = 3
    base_delay_seconds: float = 2.0
    max_delay_seconds: float = 300.0


@dataclass(slots=True)
class SubmitRequest:
    job_payload: dict[str, Any]
    idempotency_key: str | None = None
    queue: str = "default"
    tenant_id: str = "default"
    lease_seconds: int = 30
    metadata: dict[str, str] = field(default_factory=dict)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)


@dataclass(slots=True)
class SubmitResponse:
    job_id: str
    state: JobState
    accepted: bool


@dataclass(slots=True)
class ClaimRequest:
    worker_id: str
    batch_size: int = 1
    queue: str = "default"
    tenant_id: str = "default"


@dataclass(slots=True)
class CompleteRequest:
    job_id: str
    fencing_token: int
    result: dict[str, Any] | None = None


@dataclass(slots=True)
class FailRequest:
    job_id: str
    fencing_token: int
    reason: str


@dataclass(slots=True)
class WorkerRegistration:
    worker_name: str
    queue: str = "default"
    tenant_id: str = "default"
    capabilities: list[str] = field(default_factory=list)


@dataclass(slots=True)
class WorkerRegistrationResponse:
    worker_id: str
    accepted: bool
