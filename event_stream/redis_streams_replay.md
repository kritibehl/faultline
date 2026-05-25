# Redis Streams Replay Design

Faultline can use Redis Streams as an event replay layer for job lifecycle events.

## Example stream

```text
XADD faultline.job.events * event claim_job job_id job-1 worker_id worker-a fencing_token 1
XADD faultline.job.events * event lease_takeover job_id job-1 worker_id worker-b fencing_token 2
XADD faultline.job.events * event reject_stale_write job_id job-1 worker_id worker-a fencing_token 1
Use

Redis Streams are used for replay and inspection. PostgreSQL remains the correctness boundary.
