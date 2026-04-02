from common.observability.tracing import get_tracer
"""
worker/executor.py
───────────────────
Job execution lifecycle for Faultline.

Documents the execution contract that every job must satisfy and provides
utilities for execution timing and crash injection.

Execution Contract
──────────────────
A job moves through the following phases inside the worker loop:

    1. CLAIM
       claim_one_job() atomically acquires the lease and increments
       fencing_token. On return, the worker holds epoch N.

    2. PRE-EXECUTION FENCE
       assert_fence(token=N) is called before execution begins.
       This catches the case where another worker has already reclaimed
       the job (e.g. the lease expired while this worker was idle).

    3. EXECUTION
       The job payload is processed. Duration is bounded by LEASE_SECONDS.
       If execution takes longer than the lease TTL, the post-execution
       fence will catch it.

    4. POST-EXECUTION FENCE
       assert_fence(token=N) is called again after execution completes.
       This catches the case where the lease expired during execution
       (slow job, GC pause, network partition, etc.).

    5. COMMIT
       mark_succeeded() writes the ledger entry and transitions job state
       atomically. The fencing_token check in the WHERE clause provides a
       final database-layer guard even if assert_fence() is somehow bypassed.

    6. EXIT or LOOP
       On success, the worker either exits (EXIT_ON_SUCCESS=1, used in tests)
       or continues polling. On stale detection, it either exits (EXIT_ON_STALE=1)
       or continues polling.

Exactly-Once Guarantee
──────────────────────
The combination of:
    - assert_fence() blocking stale workers before commit
    - ON CONFLICT (job_id, fencing_token) DO NOTHING on ledger_entries
    - fencing_token match in the UPDATE WHERE clause

ensures that for any given (job_id, fencing_token) pair, at most one
ledger entry is ever written, regardless of retries, crashes, or races.

This is validated by tests/test_idempotent_apply.py and the 500-run
harness in tests/test_lease_race_fencing.py.
"""

import time
from typing import Callable, Any


def timed_execution(fn: Callable, *args, **kwargs) -> tuple[Any, float]:
    """
    Execute fn(*args, **kwargs) and return (result, elapsed_seconds).
    Used to measure job execution duration for metrics and TTL monitoring.
    """
    start = time.monotonic()
    result = fn(*args, **kwargs)
    elapsed = time.monotonic() - start
    return result, elapsed


def check_lease_headroom(elapsed_seconds: float, lease_seconds: int, min_headroom: float = 5.0) -> bool:
    """
    Returns True if enough lease time remains to safely attempt a commit.

    Rule of thumb: if less than min_headroom seconds remain on the lease,
    assert_fence() is likely to fail. Better to abort early than race the clock.

    This is a soft check — assert_fence() is the hard gate.
    """
    return (lease_seconds - elapsed_seconds) >= min_headroom


# Crash injection points — used by CRASH_AT env var in worker.py for drills.
# These correspond to the named points where os._exit(137) is injected.
CRASH_POINT_AFTER_LEASE = "after_lease_acquire"
CRASH_POINT_BEFORE_COMMIT = "before_commit"

tracer = get_tracer('faultline.worker.executor')
