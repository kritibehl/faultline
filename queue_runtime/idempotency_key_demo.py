from __future__ import annotations

from queue_runtime.lease_table_simulator import LeaseTableSimulator


def run_demo() -> dict[str, object]:
    table = LeaseTableSimulator()

    first = table.enqueue(
        job_id="job-1",
        payload={"task": "charge"},
        idempotency_key="payment-123",
    )

    second = table.enqueue(
        job_id="job-duplicate",
        payload={"task": "charge"},
        idempotency_key="payment-123",
    )

    worker_a_claim = table.claim("worker-a")
    assert worker_a_claim is not None
    job_id, token_a = worker_a_claim

    _, token_b = table.takeover(job_id, "worker-b")

    worker_b_committed = table.complete(
        job_id=job_id,
        worker_id="worker-b",
        submitted_fencing_token=token_b,
        result={"status": "ok"},
    )

    stale_worker_rejected = not table.complete(
        job_id=job_id,
        worker_id="worker-a",
        submitted_fencing_token=token_a,
        result={"status": "late"},
    )

    return {
        "idempotency_prevented_duplicate": first.job_id == second.job_id,
        "worker_b_committed": worker_b_committed,
        "stale_worker_rejected": stale_worker_rejected,
        "final_state": table.jobs[job_id].state,
        "final_fencing_token": table.jobs[job_id].fencing_token,
    }


if __name__ == "__main__":
    print(run_demo())
