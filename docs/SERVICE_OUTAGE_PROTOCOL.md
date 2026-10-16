# Faultline: scoped Redis and PostgreSQL service outage probes

## Scope and claim

This experiment is a **service-availability smoke test**, distinct from the worker-level crash/recovery and fencing/idempotency experiments. It verifies that a separate client on an isolated Docker network can (a) contact a healthy datastore, (b) no longer complete a request while the datastore container is paused, and (c) contact it again after `docker unpause`.

**It does not establish** that an in-flight Celery or BullMQ job survives a Redis disconnect or PostgreSQL failover. It does not simulate network partitions, database primary promotion, container restarts, data corruption, or cloud managed-service semantics. The outage is a deterministic Docker cgroup pause, **not** a real network cable disconnect. The audited outcome concerns datastore request availability and restoration, not side-effect correctness or broker acknowledgement.

## Execute

From repository root, with Docker Desktop running:

```bash
python -m faultline.outage_probe --adapter celery --service redis --dry-run
python -m faultline.outage_probe --adapter celery --service redis --pause-seconds 5 --min-free-gib 4 --cleanup-passing
python -m faultline.outage_probe --adapter bullmq --service postgres --pause-seconds 5 --min-free-gib 4 --cleanup-passing
```

Use `--adapter bullmq --service redis` or `--adapter celery --service postgres` for the other two matrix combinations. Each run creates a **new random** Compose project named `faultline-outage-<adapter>-<12 hex>`. Only `postgres` and `redis` are brought up; no worker jobs are submitted. The peer client is a short-lived `sleep` container on that isolated network, started from the same already-used Redis/PostgreSQL images. A client-side `timeout 2` protects each probe operation; a timeout in the *Docker CLI itself* is not treated as proof of an outage.

The default disk gate requires at least 4 GiB available **before** starting Docker. This is a minimum guard, not a guarantee that Docker has enough resources. The user can increase it. Tests for this module never invoke Docker.

## Evidence and interpretation

Each run writes `artifacts/outages/<timestamp>-<project>-<service>/report.json` at setup start and `compose.log` where possible. Saved records include the Compose project identity, selected adapter/service, baseline reachability, Docker paused state, the during-pause client result, restored reachability, and error/cleanup status. The peer client is always targeted for removal by the exact container ID returned from its successful creation. `finally` attempts `docker unpause` if anything fails after injection.

A `PASS` requires all three: **baseline peer request succeeded**, **the paused peer request exited with its own client timeout 124**, and **the peer request succeeded again after unpause**. Other outcomes are `INCONCLUSIVE`. No report claiming PASS is produced on a Docker CLI timeout, incomplete health check, interrupted run, or missing evidence. A result is *not* an application-level safety or recovery guarantee.

`--cleanup-passing` may run `docker compose down --volumes` **only for this run's randomly generated project** and only after a PASS plus exact Compose label, container-name, and evidence checks. Failed or inconclusive environments are retained for debugging. The cleanup never targets other projects or uses global Docker prune. This operation deletes the disposable, project-scoped Compose volumes (if present), never unrelated project volumes.

On a failed run, inspect `report.json` and project logs. If an emergency `docker unpause` failed, use the exact retained `compose_project` and `service` in the report to diagnose and recover that **one** container. Do not globally prune volumes or containers.

## Further work

Full worker-visible Redis/network partition and PostgreSQL unavailability scenarios need a transaction-aware fault scheduler running **concurrently with an active task**. They should assert delivery/ACK semantics and database invariants separately, preserve events across process restarts, and classify unavailable/incomplete evidence as `INCONCLUSIVE`. The current smoke probes deliberately make no such claim.
