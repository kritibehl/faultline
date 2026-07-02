# AWS-Style Infrastructure Readiness Report

## Purpose

Validate Faultline readiness for an AWS-style backend deployment workflow without claiming use of managed AWS services.

## Readiness checks

| Area | Evidence |
|---|---|
| Docker build | service can be packaged as container image |
| Health check | `/health` endpoint validates runtime status |
| Metrics | `/metrics` endpoint exposes operational counters |
| CI/CD | tests and smoke checks can run before deployment |
| Failure scenario | stale-worker / lease-takeover recovery validated |
| Rollback | fail closed, restore prior image, replay outbox events |
| Remediation | inspect traces, retry queue, lease state, and outbox |

## Deployment plan

```text
build image
run tests
start service
check /health
check /metrics
run failure simulation
verify duplicate commits = 0
promote only if checks pass
Failure scenario

A worker loses connectivity during an active lease. Another worker reclaims the job after lease expiry. The stale worker later reconnects and attempts a commit, but fencing-token validation rejects the stale write.

Rollback / remediation
stop unsafe worker rollout
restore prior image
preserve replay artifacts
replay unpublished outbox events
verify /health and /metrics
confirm duplicate commits remain 0
Safe claim

This is an AWS-style infrastructure readiness artifact. It does not claim EKS, Lambda, S3, DynamoDB, SQS, or production AWS deployment.
