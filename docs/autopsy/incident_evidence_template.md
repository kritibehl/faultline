# Faultline incident evidence pack

## Scenario
Lease expiry -> reclaim -> stale commit blocked

## Evidence bundle
- harness output: `tests/results/lease_race_500_runs.txt`
- trace chain: `docs/autopsy/assets/otel_trace_chain.jsonl`
- logs: `docs/autopsy/assets/logs.jsonl`
- screenshot: Jaeger trace showing submit -> claim -> execute -> complete

## Key assertions
- worker A owned the first lease before worker B launched
- worker B reclaimed only after A's lease expired
- stale write was blocked
- ledger count remained exactly 1
- final job state was `succeeded`
