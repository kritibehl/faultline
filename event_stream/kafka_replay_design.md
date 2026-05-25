
Kafka Replay Design

Kafka can act as an append-only job-event stream for Faultline.

Topic
faultline.job.events
Replay use case

Operators can reconstruct:

claim_job -> acquire_lease -> lease_takeover -> commit_result -> reject_stale_write
Safe claim

This repo documents Kafka replay design. It does not claim a production Kafka deployment.
