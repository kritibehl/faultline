# Tuning Guidance

## Key operational knobs

- `batch_size`
- `lease_duration`
- `poll_interval`
- `retry_backoff`
- `reconciler_interval`

## What each one trades

- larger `batch_size` lowers claim overhead but can worsen short-job starvation
- longer `lease_duration` reduces premature reclaim but increases crash recovery lag
- shorter `poll_interval` improves recovery time but increases coordination overhead
- more aggressive `retry_backoff` lowers coordinator churn but slows recovery of transient failures
- shorter `reconciler_interval` improves convergence but increases background load
