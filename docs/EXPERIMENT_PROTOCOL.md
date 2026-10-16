# Faultline verification protocol

## Boundary of guarantees

Faultline runs real Celery/BullMQ workers against Redis and PostgreSQL. It tests crash/replay conditions with `SIGSTOP` and `SIGKILL`, examines the durable side-effect ledger, and writes per-run evidence. Its live *observation* deadline is measured using a monotonic Python clock from successful fault injection to the runner's observation of Worker B's terminal log marker; it does **not** measure end-to-end job duration, broker acknowledgment, or total Docker environment setup. The retrospective recovery audit uses persisted event timestamps and may disagree with the live observation duration; report both measurements, not interchangeably.

For Celery, transactionally recorded `owner_token_at_commit` is compared with the token presented by the committing worker. Older effects without this evidence must be `INCONCLUSIVE`. The BullMQ example demonstrates duplicate suppression, not the same transactional fencing guarantee as Celery. Do not present BullMQ idempotency as proof of a general exactly-once execution model.

## Repeated trials

```bash
cd ~/Desktop/project-upgrades/faultline
source .framework-venv/bin/activate
python -m pytest tests/ -q
python -m faultline.trials --dry-run
python -m faultline.trials --trials 3 --cleanup-passing
```

Each trial launches an isolated Docker Compose project. This utility never cleans up failed/inconclusive runs. `--cleanup-passing` is opt-in, and any removal is delegated to `faultline.cleanup_run`, which independently checks retained evidence and scope. Without that option, successful experiments also retain containers and volumes. The runner stops scheduling additional experiments if free disk space is below `--min-free-gib` (default 4). This is a guardrail, not an assurance about Docker image/volume usage.

Results are saved in `artifacts/benchmarks/<UTC>-<suffix>/`: `manifest.json` (updated after every trial), `summary.json`, `SUMMARY.md`, and one combined subprocess log per trial. Linked per-run directories under `artifacts/runs/` contain the durable source evidence. An externally interrupted batch may have a partial `manifest.json`; never describe it as completed.

The default cases are one safe Celery fenced pause/pre-commit trial and one BullMQ idempotent kill/post-commit trial. To include a deliberately unsafe negative control:

```bash
python -m faultline.trials --cases celery-fenced,bullmq-idempotent,celery-unsafe-control --trials 3 --cleanup-passing
```

The negative control is *expected to detect* a violation; its nonzero `faultline test` exit is not an infrastructure error if a complete, matching report demonstrates the invariant `FAIL`. Its preserved containers are **not** automatically cleaned. A test is `VERIFIED_PASS` only when exit status, selected invariant, live monotonic observation, retrospective recovery audit, and all required evidence agree. For Celery, transactional ownership must also be `PASS`. An aborted runner, missing report, inconsistent evidence, or observation timeout is `INCONCLUSIVE`, not a successful safety/liveness result. Reports count every attempted trial, including inconclusives.

p50 is the median; p95 uses the nearest-rank empirical estimator. Both use **only verified passing** observations. Report the denominator and the excluded failures; a small sample does not demonstrate production reliability or a statistically stable tail latency.

## CI and validation

A GitHub Actions workflow runs syntax validation, unit/regression tests, and a read-only trial plan on pushes and pull requests. Expensive Docker integration is manually enabled with the `run_live` workflow-dispatch input. The CI workflow must actually run successfully in GitHub before claiming CI verification. A manually dispatched job can fail because ephemeral runner resources differ; preserve and inspect uploaded forensic evidence instead of hiding an infrastructure failure.

## Remaining limitations

Real broker/database interruption tests (Redis partition, PostgreSQL disconnect) are **not** implemented by this batch runner, and must not be claimed as verified. Faultline's runner-level observation timeout does not terminate arbitrary orphaned Docker processes or prove permanent liveness failure. The current experiments exercise controlled fault windows, not arbitrary production schedules. Honest benchmarking should include multiple independent runs, failures, environment/hardware specifications, and documented cleanup of verified projects.
