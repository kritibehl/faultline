# gRPC Service Contract Example

## Purpose

This contract shows how Faultline's distributed job execution model can be exposed through service boundaries.

## Services

- `SubmitJob`
- `ClaimJob`
- `CommitJob`
- `GetJobHealth`

## Reliability fields

- `idempotency_key`
- `worker_id`
- `fencing_token`
- `stale_worker_rejected`
- `duplicate_risk`

## Safe claim

This is a gRPC-style service contract example for backend/platform review. It does not claim a deployed production gRPC service.
