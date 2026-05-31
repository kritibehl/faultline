from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256


@dataclass
class OutboxEvent:
    event_id: str
    job_id: str
    idempotency_key: str
    event_type: str
    payload: dict
    published: bool = False


@dataclass
class TransactionalOutbox:
    events: dict[str, OutboxEvent] = field(default_factory=dict)
    idempotency_index: set[str] = field(default_factory=set)
    duplicates_prevented: int = 0
    idempotency_violations: int = 0

    def idempotency_key(self, job_id: str, event_type: str, payload: dict) -> str:
        raw = f"{job_id}:{event_type}:{sorted(payload.items())}"
        return sha256(raw.encode()).hexdigest()

    def write_event(self, job_id: str, event_type: str, payload: dict) -> bool:
        key = self.idempotency_key(job_id, event_type, payload)
        if key in self.idempotency_index:
            self.duplicates_prevented += 1
            return False

        event_id = f"evt-{len(self.events) + 1}"
        self.events[event_id] = OutboxEvent(
            event_id=event_id,
            job_id=job_id,
            idempotency_key=key,
            event_type=event_type,
            payload=payload,
        )
        self.idempotency_index.add(key)
        return True

    def replay_publish(self) -> int:
        published = 0
        for event in self.events.values():
            if not event.published:
                event.published = True
                published += 1
        return published

    def report(self) -> dict[str, int]:
        lost_events = sum(1 for event in self.events.values() if not event.published)
        return {
            "events_written": len(self.events),
            "duplicates_prevented": self.duplicates_prevented,
            "lost_events": lost_events,
            "idempotency_violations": self.idempotency_violations,
        }


def run_outbox_demo() -> dict[str, int]:
    outbox = TransactionalOutbox()

    for i in range(500):
        outbox.write_event(
            job_id=f"job-{i}",
            event_type="job.completed",
            payload={"status": "ok", "index": i},
        )

    for i in range(37):
        outbox.write_event(
            job_id=f"job-{i}",
            event_type="job.completed",
            payload={"status": "ok", "index": i},
        )

    outbox.replay_publish()
    return outbox.report()


if __name__ == "__main__":
    print(run_outbox_demo())
