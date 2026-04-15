# Faultline++ Roadmap

Faultline is evolving from a correctness-proven queue implementation into a distributed execution correctness framework.

## Framework-grade pillars

### 1. Public API / SDK
- Python SDK
- minimal Go client
- typed request/response contracts
- tenant-aware enqueue and worker registration surface

### 2. Multi-process service boundary
- producer API
- claim / coordination layer
- worker process
- reconciler daemon
- metrics/export service

### 3. External side-effect safety
- outbox / idempotency wrapper
- downstream contract guidance
- boundary between ledger correctness and external effect safety

### 4. Operator tuning
- batch-size guidance
- polling policy hints
- safe-for-production grading
- workload-shape-based recommendations

### 5. Formal correctness
- invariant catalog
- state model
- lease lifecycle reasoning
- correctness score / near-miss reporting

## End-state
Faultline++ should look like a reusable platform primitive for correctness-sensitive execution under partial failure.
