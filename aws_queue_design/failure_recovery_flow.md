
Failure Recovery Flow
Normal recovery
worker claims job
worker stalls
lease expires
new worker takes over
fencing token advances
new worker commits
stale worker wakes up
stale commit rejected
Retry recovery
worker fails transiently
retry_count increments
next_run_at scheduled
job becomes eligible again
new attempt receives current fencing token
DLQ-style recovery
max retries exceeded
job moves to dead-letter/review state
operator inspects trace/replay artifacts
controlled replay decision made
Customer impact

Recovery paths should be observable, bounded, and safe against duplicate commits.
