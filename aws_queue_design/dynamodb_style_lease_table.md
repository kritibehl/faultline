
DynamoDB-Style Lease Table Design

Safe claim: this is a DynamoDB-style lease-table design artifact, not a deployed DynamoDB implementation.

Table model
Field	Purpose
job_id	primary identifier
state	queued/running/succeeded/failed
lease_owner	current worker
lease_expires_at	reclaim boundary
fencing_token	monotonic ownership version
retry_count	retry tracking
updated_at	operational debugging
Conditional write idea

A valid commit requires:

current_fencing_token == submitted_fencing_token

This mirrors the same correctness idea Faultline uses with PostgreSQL.
