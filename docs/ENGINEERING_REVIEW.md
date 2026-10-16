# Faultline — final engineering review and verification checklist

## System under test

Faultline is a fault-injection test harness for payment-like background job side effects. Python adapters orchestrate real Docker-based Celery/Redis/PostgreSQL and Node.js BullMQ/Redis/PostgreSQL jobs in unique Compose project namespaces. Redis handles queue delivery; PostgreSQL stores job ownership/fencing tokens, attempts, accepted side effects, and stale rejections. The orchestrator pauses/kills a worker at selected pre/post-commit windows to force re-delivery or stalled-job processing.

The actual contract being evaluated is deliberately narrower than exactly-once task execution:

- **Safety**: an at-most-one-effect ledger, transaction-level fencing-token checks for stale owners on Celery, and/or an idempotency key for duplicate side-effect suppression.
- **Liveness evidence**: observation of Worker B's durable-effect terminal marker within a monotonic 60-second **post-injection observation window**. The separate retrospective audit checks timestamped worker/database history and can be PASS, FAIL, or INCONCLUSIVE.
- **Forensics**: immutable run-specific history, worker logs, PostgreSQL effect and rejection snapshots, recovery reports, and explicit failure tombstones. Failure to observe is not silently promoted into a correctness verdict.

## Reproducing the core claims

```bash
python -m pytest tests/ -q
python -m faultline.trials --dry-run
python -m faultline.trials --cases celery-fenced,bullmq-idempotent --trials 1 --min-free-gib 4 --cleanup-passing
python -m faultline.trials --cases celery-unsafe-control --trials 1 --min-free-gib 4
```

Only the first two commands are light tests: the live trials require Docker, disk headroom, and time. An unsafe control returning a safety `FAIL` is **expected positive detection** but may deliberately preserve that project's Docker environment; do not equate it with a safe implementation PASS.

For separately scoped Redis/PostgreSQL service pause/restoration tests, see [SERVICE_OUTAGE_PROTOCOL.md](SERVICE_OUTAGE_PROTOCOL.md). These do not execute a worker job and must not be described as in-flight worker failover tests.

## Independently reviewed evidence from the user's local logs (2026-10-16)

- At revision `00f2433`, **165 Python regression/unit tests** passed locally.
- Two real sequential benchmark trials returned `VERIFIED_PASS`: Celery fenced pre-commit recovery (live observation **33.859 s**) and BullMQ idempotent post-commit recovery (live observation **12.716 s**). Both observed one committed side effect.
- An earlier deliberately unsafe Celery pre-commit control yielded two accepted effects. The ownership auditor detected Worker A presenting token 1 when the commit-time owner token was 2.
- One-second Celery deadline injection produced preserved `OBSERVATION_TIMEOUT` evidence with `INCONCLUSIVE` safety and recovery, rather than false FAIL.

These are **single-trial observations, not estimated failure probabilities or SLOs**. The single-sample p50/p95 statistics printed by the batch runner cannot establish a tail latency distribution. Several different timing measures exist; the live monotonic measurement must not be conflated with the PostgreSQL-event retrospective audit or total wall-clock setup time.

## Limitations and risk register

1. Redis/PostgreSQL startup on resource-constrained laptops can be slow or transiently unhealthy. Docker setup time is outside the live 60-second observation window; a startup failure produces incomplete-run evidence instead of safety FAIL.
2. The CLI's `no-lost-committed-effect` property is scoped to the checked transaction ledger and observed experiment. It is not a proof of cross-service end-to-end exactly-once execution.
3. The current tests cover selected failure windows and workload parameters; broadened fault schedules, network partitions, persistent outages, throughput saturation, transaction retries, and more repetitions are future work.
4. **Automated CI verified as of 2026-10-16:** public GitHub Actions history shows successful `Faultline tests #1` and `Faultline CI #115` runs for commit `00f2433` on `feat/p0-invariant-recovery`. This verifies those workflow executions, **not** future changes or the manual live jobs. Live Docker worker trials and service-outage jobs remain opt-in through `workflow_dispatch`.
5. `artifacts/benchmarks/` and `artifacts/outages/` may be intentionally untracked. Review and selectively publish sanitized representative evidence rather than blindly committing local/generated logs.

## Release checklist

- Run the complete unit suite and compile check after every source change.
- Verify GitHub Actions **unit** workflow shows success on the intended branch; manually trigger the optional live jobs before claiming CI integration verified.
- Run at least one adversarial known-unsafe control and verify a correctly detected violation.
- Capture test counts, environment versions, Git SHA, denominators, and full paths to immutable artifacts for any benchmark claim.
- Never clean or reset unrelated Docker projects. Only use evidence-backed cleanup for exact namespaced Compose projects.
- Keep the README's headline metric tied to an explicit measured run and avoid unverified reliability/scale claims.
