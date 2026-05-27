from queue_runtime.idempotency_key_demo import run_demo
from queue_runtime.lease_table_simulator import LeaseTableSimulator
from queue_runtime.worker_retry_queue import RetryQueue


def test_idempotency_key_prevents_duplicate_submission():
    table = LeaseTableSimulator()

    first = table.enqueue("job-1", {"task": "a"}, "idem-1")
    second = table.enqueue("job-2", {"task": "a"}, "idem-1")

    assert first.job_id == "job-1"
    assert second.job_id == "job-1"
    assert len(table.jobs) == 1


def test_stale_worker_commit_is_rejected_after_takeover():
    table = LeaseTableSimulator()
    table.enqueue("job-1", {"task": "a"}, "idem-1")

    job_id, token_a = table.claim("worker-a")
    _, token_b = table.takeover(job_id, "worker-b")

    assert table.complete(job_id, "worker-b", token_b, {"ok": True}) is True
    assert table.complete(job_id, "worker-a", token_a, {"late": True}) is False
    assert table.jobs[job_id].result == {"ok": True}


def test_retry_queue_routes_to_dead_letter_after_max_retries():
    retry_queue = RetryQueue(max_retries=3)

    retry_queue.schedule_retry("job-1", retry_count=1)
    retry_queue.schedule_retry("job-2", retry_count=3)

    assert retry_queue.pop_next() == "job-1"
    assert retry_queue.dead_letter == ["job-2"]


def test_demo_proves_duplicate_prevention_and_stale_rejection():
    result = run_demo()

    assert result["idempotency_prevented_duplicate"] is True
    assert result["worker_b_committed"] is True
    assert result["stale_worker_rejected"] is True
    assert result["final_state"] == "succeeded"
    assert result["final_fencing_token"] == 2
