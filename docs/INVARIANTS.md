# Invariants

Faultline maintains these invariants:

1. At most one valid commit per lease epoch
2. Lower fencing token commits must be rejected once ownership advances
3. Reconciliation must converge incomplete work to a reclaimable state
4. Duplicate submission must not create duplicate committed side effects within the fenced path
