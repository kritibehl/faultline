# Network Partition Correctness Report

## Purpose

Validate Faultline correctness when a worker loses database/network access during active execution.

## Scenario

```text
worker-a claims job
worker-a loses DB/network access
heartbeat stops
lease expires
worker-b reclaims job
fencing token advances
worker-b commits
partition heals
worker-a attempts stale commit
PostgreSQL fencing validation rejects worker-a
Correctness result
Signal	Result
duplicate commits	0
stale writes rejected	1
partition recovery time	18,000 ms
final state	consistent
Why this matters

A partitioned worker can continue running locally, but it must not be allowed to commit after ownership changes. Faultline's fencing-token boundary prevents stale writes after partition recovery.

Safe claim

This report validates simulated network-partition correctness using Faultline fault profiles and replay artifacts.
