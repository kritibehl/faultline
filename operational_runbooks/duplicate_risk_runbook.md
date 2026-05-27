# Duplicate Risk Runbook

## Symptoms

- duplicate-risk count rises
- retry amplification increases
- queue backlog grows
- stale-worker rejection events increase

## Triage

1. Confirm duplicate commit rate remains 0.0%.
2. Inspect stale-worker rejection traces.
3. Check retry growth and queue depth.
4. Review idempotency key behavior.

## Operator decision

If duplicate risk rises but commits are rejected, continue with monitoring. If commit validation is unavailable, fail closed or pause unsafe processing.
