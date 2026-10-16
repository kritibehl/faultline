"""Best-effort forensic evidence for interrupted real-worker experiments.

An interrupted observation is not a demonstrated safety violation or liveness failure.
The original exception is always re-raised; capture failures are reported separately.
"""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def _exception_summary(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"[:2000]


def write_failure_evidence(
    *,
    run_dir: Path,
    adapter: str,
    compose_project: str,
    job_id: str,
    mode: str,
    fault: str,
    window: str,
    invariant: str,
    stage: str,
    error: BaseException,
    orchestrator_events: list[Any],
    load_db_events: Callable[[], list[Any]],
    worker_logs: dict[str, Callable[[], str]],
) -> dict[str, Any]:
    """Persist partial evidence. Never infer PASS/FAIL from an aborted run."""
    run_dir.mkdir(parents=True, exist_ok=True)
    # Write a minimal durable tombstone before optional Docker/DB queries.
    # Even if evidence collection itself fails, the run is not mistaken for a pass.
    _atomic_json(run_dir / "run-failure.json", {
        "schema_version": 1,
        "run_status": "ERROR",
        "invariant_result": "INCONCLUSIVE",
        "recovery_result": "INCONCLUSIVE",
        "evidence_capture": "IN_PROGRESS",
        "adapter": adapter,
        "compose_project": compose_project,
        "job_id": job_id,
        "stage": stage,
        "error_type": type(error).__name__,
        "error_message": str(error)[:2000],
        "recorded_at": _now(),
    })
    collection_errors: dict[str, str] = {}
    events = []
    for raw in orchestrator_events:
        try:
            events.append(asdict(raw))
        except (TypeError, ValueError) as exc:
            collection_errors["orchestrator_history"] = _exception_summary(exc)

    db_history_status = "NOT_ATTEMPTED"
    if stage not in ("environment_setup", "job_submission"):
        try:
            db_events = load_db_events()
            events.extend(asdict(item) for item in db_events)
            db_history_status = "COLLECTED"
        except Exception as exc:
            db_history_status = "UNAVAILABLE"
            collection_errors["database_history"] = _exception_summary(exc)

    events.append({
        "ts": _now(),
        "type": "runner_failed",
        "job_id": job_id,
        "worker": "orchestrator",
        "details": {"stage": stage, "error_type": type(error).__name__},
    })
    events.sort(key=lambda item: str(item.get("ts", "")))
    (run_dir / "history.jsonl").write_text(
        "".join(json.dumps(event, sort_keys=True, default=str) + "\n" for event in events),
        encoding="utf-8",
    )

    log_status = {}
    for worker, loader in worker_logs.items():
        try:
            contents = loader()
            (run_dir / f"{worker}.log").write_text(contents, encoding="utf-8")
            log_status[worker] = "CAPTURED" if contents else "EMPTY_OR_UNAVAILABLE"
        except Exception as exc:
            log_status[worker] = "UNAVAILABLE"
            collection_errors[f"{worker}_logs"] = _exception_summary(exc)

    message = str(error).lower()
    if isinstance(error, KeyboardInterrupt):
        failure_kind = "INTERRUPTED"
    elif "timed out waiting" in message or isinstance(error, TimeoutError):
        failure_kind = "OBSERVATION_TIMEOUT"
    elif isinstance(error, OSError):
        failure_kind = "INFRASTRUCTURE_ERROR"
    else:
        failure_kind = "RUNNER_ERROR"

    result = {
        "schema_version": 1,
        "framework": "faultline",
        "adapter": adapter,
        "compose_project": compose_project,
        "job_id": job_id,
        "mode": mode,
        "fault": fault,
        "window": window,
        "invariant": invariant,
        "run_status": "ERROR",
        "invariant_result": "INCONCLUSIVE",
        "recovery_result": "INCONCLUSIVE",
        "evidence_capture": "COMPLETE",
        "failure_kind": failure_kind,
        "stage": stage,
        "error_type": type(error).__name__,
        "error_message": str(error)[:2000],
        "recorded_at": _now(),
        "history_event_count": len(events),
        "database_history_status": db_history_status,
        "worker_log_status": log_status,
        "collection_errors": collection_errors,
        "interpretation": (
            "Runner stopped without complete verification; a timeout in observation "
            "does not by itself prove a permanent liveness failure."
        ),
    }
    _atomic_json(run_dir / "run-failure.json", result)
    return result


@contextmanager
def preserve_failed_run(
    *,
    run_dir: Path,
    adapter: str,
    compose_project: str,
    job_id: str,
    mode: str,
    fault: str,
    window: str,
    invariant: str,
    stage: dict[str, str],
    orchestrator_events: list[Any],
    load_db_events: Callable[[], list[Any]],
    worker_logs: dict[str, Callable[[], str]],
) -> Iterator[None]:
    try:
        yield
    except BaseException as original:
        try:
            result = write_failure_evidence(
                run_dir=run_dir,
                adapter=adapter,
                compose_project=compose_project,
                job_id=job_id,
                mode=mode,
                fault=fault,
                window=window,
                invariant=invariant,
                stage=stage["name"],
                error=original,
                orchestrator_events=orchestrator_events,
                load_db_events=load_db_events,
                worker_logs=worker_logs,
            )
            print(
                f"Faultline failure evidence: {run_dir / 'run-failure.json'} "
                f"({result['failure_kind']}; invariant INCONCLUSIVE)",
                file=sys.stderr,
            )
        except Exception as capture_error:
            print(
                f"FAULTLINE EVIDENCE CAPTURE ERROR: {_exception_summary(capture_error)}; "
                f"original error: {_exception_summary(original)}",
                file=sys.stderr,
            )
        raise
