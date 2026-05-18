
Case Study: Stale-Worker Corruption
Failure
Worker A claims a job with fencing token 1.
Worker A stalls.
The lease expires.
Worker B reclaims the job and advances the fencing token to 2.
Worker B commits successfully.
Worker A wakes up and attempts a late commit.
Naive lease-only behavior

The stale worker can commit late, creating duplicate side effects.

Faultline behavior

Faultline validates the submitted fencing token at the PostgreSQL commit boundary.

Worker A submits token 1, but the database has current token 2.

Result:

reject_stale_write
Engineering lesson

Lease expiry is not enough. Commit authority must be validated against a monotonic fencing token at the shared correctness boundary.
