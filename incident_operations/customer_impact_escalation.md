# Customer Impact Escalation

## Escalation triggers

Escalate when:

- duplicate-risk increases across multiple windows
- retry amplification causes queue backlog growth
- PostgreSQL commit validation becomes unavailable
- stale-worker rejection spikes above normal baseline
- customer-facing workload delay exceeds threshold

## Escalation summary fields

- affected workload
- queue depth
- retry growth
- expired lease count
- stale-worker rejection count
- duplicate commit count
- safe_to_operate status
- replay artifact link

## Operator decision

If duplicate commits remain prevented and the system is safely rejecting stale writes, continue mitigation and monitoring.

If commit validation cannot run, pause unsafe processing or fail closed.
