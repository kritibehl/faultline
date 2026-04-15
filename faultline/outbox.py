from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class OutboxEnvelope:
    job_id: str
    fencing_token: int
    idempotency_key: str
    destination: str
    payload: dict[str, Any]


def wrap_external_effect(*, job_id: str, fencing_token: int, destination: str, payload: dict[str, Any]) -> OutboxEnvelope:
    """
    Wrap an external side effect with a deterministic idempotency key.

    This does not make arbitrary downstream systems exactly-once.
    It makes them safer to integrate by turning the execution epoch into
    an explicit idempotency contract.
    """
    return OutboxEnvelope(
        job_id=job_id,
        fencing_token=fencing_token,
        idempotency_key=f"{job_id}:{fencing_token}:{destination}",
        destination=destination,
        payload=payload,
    )
