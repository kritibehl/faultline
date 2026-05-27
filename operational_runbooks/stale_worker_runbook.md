# Stale Worker Recovery Runbook

## Symptoms

- expired lease count increases
- stale-write rejection count increases
- trace contains `reject_stale_write`
- worker resumes after lease takeover

## Triage

1. Check `/health`.
2. Check `/metrics`.
3. Inspect trace export.
4. Confirm current fencing token.
5. Verify stale worker commit was rejected.

## Recovery

- keep job committed by current owner
- terminate or restart stale worker if stuck
- tune lease duration if premature expiry is common
