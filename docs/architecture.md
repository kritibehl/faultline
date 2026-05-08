# Faultline Architecture

```text
Producer
   |
   v
Job Queue Table
   |
   +--> Worker A claims lease, token=1
   |
   +--> Worker B later reclaims expired lease, token=2
   |
   v
PostgreSQL correctness boundary
   |
   +--> commit accepted only if fencing_token matches current token
   +--> stale writes rejected
Components
producer API
PostgreSQL-backed job table
worker processes
lease / fencing-token ownership
commit log
reconciler
metrics/export surface
Key principle

Workers may execute stale work.

Workers may not commit stale work.
