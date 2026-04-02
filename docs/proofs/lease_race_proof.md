# Deterministic Lease-Race Proof

This proof validates the hardest Faultline invariant:

- worker A claims job first
- worker A loses lease
- worker B reclaims same job with a higher fencing token
- stale completion from worker A is rejected
- job still finishes exactly once

## Run

```bash
./scripts/run_controlled_race.sh

```bash
cat > docs/incidents/incident_pack.md <<'MD'
# Faultline Incident Pack

Each controlled race should produce:

- raw artifact JSON
- timeline markdown
- explanation markdown
- DetTrace export JSONL

This package is the public proof surface for:
- claim ordering
- lease loss
- reclaim
- stale write prevention
- terminal success correctness
