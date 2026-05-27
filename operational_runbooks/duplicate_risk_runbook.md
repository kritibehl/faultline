# Duplicate Risk Runbook

## Symptoms

- duplicate-risk count increases
- retry amplification increases
- queue depth grows
- stale-worker rejections increase

## Triage

1. Confirm duplicate commit rate remains 0.0%.
2. Inspect stale-write rejection events.
3. Review retry growth and queue delay.
4. Validate idempotency-key behavior.

## Decision

If duplicate-risk is rising but stale commits are rejected, continue monitoring. If commit validation cannot run, pause unsafe processing or fail closed.
