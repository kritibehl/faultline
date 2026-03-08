# Postmortem — Reclaim Race Walkthrough

## Timeline

    t=0.000  Worker A claims job: fencing_token=1, lease_expires_at=NOW()+1s
    t=0.001  Worker B starts polling — job is running, lease not expired
    t=1.001  Lease expires
    t=1.001  Worker B reclaims: fencing_token=2, new lease
    t=1.500  Worker A wakes, calls assert_fence(token=1)
               current_token=2 → 1 != 2 → stale_write_blocked
               Worker A raises RuntimeError("stale_token")
    t=1.501  Worker B calls assert_fence(token=2) → ok
    t=1.501  Worker B: INSERT ledger(job_id, fencing_token=2) → 1 row
             UPDATE jobs SET state='succeeded'

    Final: ledger_entries.count=1. Zero duplicates.

## Without Fencing (the bug)

    t=1.500  Worker A: INSERT ledger → 1st row
    t=1.501  Worker B: INSERT ledger → 2nd row (DUPLICATE)
    Result: account credited twice, job processed twice.

## Defense Layers

Layer 1 — assert_fence(): checks fencing_token match + lease validity before every write.
Layer 2 — UNIQUE(job_id, fencing_token): DB rejects second insert even if Layer 1 has a bug.

## Validation

    500 runs: 0 duplicates, stale_write_blocked every time.

    make lease-race-500
    python3 services/cli/scenario_runner.py reclaim-race --report
