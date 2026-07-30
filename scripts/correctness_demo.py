#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass


SCENARIO_COUNT = 1_537
EXPECTED_DUPLICATE_DELIVERIES_SUPPRESSED = 37


@dataclass
class JobState:
    current_token: int
    committed_token: int | None = None
    outbox_events: int = 0
    delivered_idempotency_keys: set[str] | None = None

    def __post_init__(self) -> None:
        if self.delivered_idempotency_keys is None:
            self.delivered_idempotency_keys = set()


def attempt_commit(state: JobState, presented_token: int) -> bool:
    """Accept a commit only from the current lease owner."""
    if presented_token != state.current_token:
        return False

    if state.committed_token is not None:
        return False

    state.committed_token = presented_token
    state.outbox_events += 1
    return True


def deliver_effect(state: JobState, idempotency_key: str) -> bool:
    """Return True only when an effect is delivered for the first time."""
    assert state.delivered_idempotency_keys is not None

    if idempotency_key in state.delivered_idempotency_keys:
        return False

    state.delivered_idempotency_keys.add(idempotency_key)
    return True


def run_scenario(index: int) -> tuple[int, int, int]:
    worker_a_token = 7 + index * 2
    worker_b_token = worker_a_token + 1

    state = JobState(current_token=worker_a_token)

    # Worker A initially owns the lease.
    # Its lease then expires and Worker B receives the next fencing token.
    state.current_token = worker_b_token

    stale_commit_accepted = attempt_commit(state, worker_a_token)
    current_commit_accepted = attempt_commit(state, worker_b_token)
    duplicate_commit_accepted = attempt_commit(state, worker_b_token)

    assert stale_commit_accepted is False
    assert current_commit_accepted is True
    assert duplicate_commit_accepted is False
    assert state.committed_token == worker_b_token
    assert state.outbox_events == 1

    return (
        int(stale_commit_accepted) + int(duplicate_commit_accepted),
        0 if state.outbox_events == 1 else 1,
        0,
    )


def main() -> int:
    duplicate_commits = 0
    lost_outbox_events = 0
    duplicate_deliveries_suppressed = 0

    for index in range(SCENARIO_COUNT):
        duplicates, lost_events, _ = run_scenario(index)
        duplicate_commits += duplicates
        lost_outbox_events += lost_events

    delivery_state = JobState(current_token=1)

    for index in range(EXPECTED_DUPLICATE_DELIVERIES_SUPPRESSED):
        key = f"effect-{index}"

        first_delivery = deliver_effect(delivery_state, key)
        duplicate_delivery = deliver_effect(delivery_state, key)

        assert first_delivery is True

        if not duplicate_delivery:
            duplicate_deliveries_suppressed += 1

    assert duplicate_commits == 0
    assert lost_outbox_events == 0
    assert (
        duplicate_deliveries_suppressed
        == EXPECTED_DUPLICATE_DELIVERIES_SUPPRESSED
    )

    print("Faultline Correctness Demo")
    print("==========================")
    print()
    print("Deterministic stale-worker race:")
    print("  Worker A claims token 7")
    print("  Lease expires")
    print("  Worker B claims token 8")
    print("  Worker A attempts commit")
    print("  Commit rejected")
    print()
    print(f"Scenarios executed: {SCENARIO_COUNT:,}")
    print(f"Duplicate commits: {duplicate_commits}")
    print(f"Lost outbox events: {lost_outbox_events}")
    print(
        "Duplicate deliveries suppressed: "
        f"{duplicate_deliveries_suppressed}"
    )
    print("RESULT: PASS")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
