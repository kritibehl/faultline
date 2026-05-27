
Customer Workload Scenarios
Scenario 1: Financial workflow

Duplicate commits can cause duplicate downstream side effects.

Faultline behavior:

stale commit rejected
duplicate-risk surfaced
replay artifact available
Scenario 2: Batch processing

A worker stalls during long-running work.

Faultline behavior:

lease expires
another worker takes over
stale worker cannot commit late
Scenario 3: Operational incident

Retry storm increases queue backlog.

Faultline behavior:

retry amplification visible
queue growth visible
operator reviews risk before unsafe acceptance
Customer-impact framing

Delayed jobs are visible and recoverable. Silent duplicate commits are harder to detect and more damaging.
