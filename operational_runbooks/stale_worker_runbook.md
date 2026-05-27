# Stale Worker Runbook

## Symptoms

- stale-write rejection count increases
- worker resumes after lease expiry
- trace shows `reject_stale_write`
- lease owner changed before late commit

## Triage

1. Check `/health`.
2. Check `/metrics`.
3. Inspect trace export.
4. Confirm current fencing token.
5. Verify stale commit was rejected.

## Recovery

- restart stuck worker if needed
- tune lease duration if false takeovers are common
- preserve replay artifacts for incident review
