from __future__ import annotations

import json
import subprocess
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from faultline.history import HistoryEvent, now_iso, write_jsonl
from faultline.adapters.base import (
    AdapterCapabilities,
    RunError,
)
from faultline.faults.base import FaultInjector
from faultline.faults.process import (
    DockerProcessKillFault,
    DockerProcessPauseFault,
)
from faultline.invariants.effects import at_most_one_effect
from faultline.lifecycle import RunLifecycle


COMPOSE = "integrations/celery/docker-compose.yml"

WORKER_A = "faultline-celery-worker-a"
WORKER_B = "faultline-celery-worker-b"
POSTGRES = "faultline-celery-postgres"


CAPABILITIES = AdapterCapabilities(
    process_pause=True,
    process_kill=True,
    broker_disconnect=False,
    redelivery=True,
    visibility_expiry=True,
)


def run(
    *args: str,
    capture: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        check=check,
    )


def compose(*args: str, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return run(
        "docker",
        "compose",
        "-f",
        COMPOSE,
        *args,
        capture=capture,
    )


def logs(container: str) -> str:
    result = run("docker", "logs", container, check=False)
    return result.stdout or ""


def wait_for_log(
    container: str,
    needle: str,
    timeout: int = 45,
) -> None:
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if needle in logs(container):
            return
        time.sleep(0.5)

    raise RunError(
        f"timed out waiting for {needle!r} in {container}"
    )


def sql(query: str) -> str:
    result = run(
        "docker",
        "exec",
        POSTGRES,
        "psql",
        "-U",
        "faultline",
        "-d",
        "faultline",
        "-At",
        "-F",
        "\t",
        "-c",
        query,
    )

    return (result.stdout or "").strip()


def parse_attempt_history(job_id: str) -> list[HistoryEvent]:
    output = sql(
        f"""
        SELECT
            created_at,
            worker_name,
            fencing_token,
            phase
        FROM attempts
        WHERE job_id = '{job_id}'
        ORDER BY created_at, id;
        """
    )

    events: list[HistoryEvent] = []

    if not output:
        return events

    for line in output.splitlines():
        ts, worker, token, phase = line.split("\t", 3)

        events.append(
            HistoryEvent(
                ts=ts,
                type=phase,
                job_id=job_id,
                worker=worker,
                fencing_token=int(token),
            )
        )

    return events


def query_effects(job_id: str) -> list[dict[str, object]]:
    output = sql(
        f"""
        SELECT
            worker_name,
            fencing_token,
            amount,
            committed_at
        FROM effects
        WHERE job_id = '{job_id}'
        ORDER BY id;
        """
    )

    effects: list[dict[str, object]] = []

    if not output:
        return effects

    for line in output.splitlines():
        worker, token, amount, committed_at = line.split("\t", 3)

        effects.append(
            {
                "worker": worker,
                "fencing_token": int(token),
                "amount": int(amount),
                "committed_at": committed_at,
            }
        )

    return effects


def query_rejections(job_id: str) -> list[dict[str, object]]:
    output = sql(
        f"""
        SELECT
            worker_name,
            presented_token,
            current_token,
            rejected_at
        FROM stale_rejections
        WHERE job_id = '{job_id}'
        ORDER BY id;
        """
    )

    rows: list[dict[str, object]] = []

    if not output:
        return rows

    for line in output.splitlines():
        worker, presented, current, rejected_at = line.split("\t", 3)

        rows.append(
            {
                "worker": worker,
                "presented_token": int(presented),
                "current_token": int(current),
                "rejected_at": rejected_at,
            }
        )

    return rows


def current_token(job_id: str) -> int:
    value = sql(
        f"""
        SELECT current_token
        FROM job_ownership
        WHERE job_id = '{job_id}';
        """
    )

    return int(value)


def fresh_environment() -> None:
    compose(
        "down",
        "-v",
        "--remove-orphans",
        capture=False,
    )

    compose(
        "build",
        capture=False,
    )

    compose(
        "up",
        "-d",
        "postgres",
        "redis",
        "worker-a",
        capture=False,
    )

    wait_for_log(
        WORKER_A,
        "ready.",
        timeout=45,
    )


def submit(
    mode: str,
    job_id: str,
    window: str,
) -> None:
    result = compose(
        "run",
        "--rm",
        "client",
        "--mode",
        mode,
        "--window",
        window,
        "--job-id",
        job_id,
    )

    if result.stdout:
        print(result.stdout.strip())


def fault_window_marker(window: str) -> str:
    if window == "pre-commit":
        return "READY_TO_COMMIT"

    if window == "post-commit":
        return "READY_AFTER_COMMIT"

    raise ValueError(
        f"unsupported window: {window!r}"
    )


def worker_b_terminal_marker(
    mode: str,
    window: str,
) -> str:
    if (
        mode == "idempotent"
        and window == "post-commit"
    ):
        return "DUPLICATE_SUPPRESSED"

    return "COMMIT_ACCEPTED"


def worker_a_terminal_marker(
    mode: str,
    window: str,
) -> str:
    if window == "post-commit":
        return "POST_COMMIT_WINDOW_EXIT"

    if mode == "unsafe":
        return "COMMIT_ACCEPTED"

    if mode == "fenced":
        return "COMMIT_REJECTED"

    if mode == "idempotent":
        return "DUPLICATE_SUPPRESSED"

    raise ValueError(
        f"unsupported mode: {mode!r}"
    )


def build_fault_injector(fault: str) -> FaultInjector:
    if fault == "pause":
        return DockerProcessPauseFault(run)

    if fault == "kill":
        return DockerProcessKillFault(run)

    raise ValueError(
        f"Celery adapter does not support fault={fault!r}"
    )


class CeleryRunLifecycle(RunLifecycle):
    """Cleanup actions owned by one Celery correctness run."""

    def __init__(self, fault: str) -> None:
        self._injector = build_fault_injector(fault)

    def cleanup(self) -> None:
        """Best-effort recovery of Worker A after a runner failure."""
        self._injector.recover(
            WORKER_A,
            check=False,
        )


def build_run_lifecycle(fault: str) -> RunLifecycle:
    return CeleryRunLifecycle(fault)


def _run_race(
    mode: str,
    fault: str = "pause",
    window: str = "pre-commit",
) -> tuple[dict[str, object], Path]:
    if mode not in {
        "unsafe",
        "fenced",
        "idempotent",
    }:
        raise ValueError(
            "mode must be unsafe, fenced, or idempotent"
        )

    if window not in {
        "pre-commit",
        "post-commit",
    }:
        raise ValueError(
            "window must be pre-commit or post-commit"
        )

    if fault == "kill" and window != "post-commit":
        raise RunError(
            "kill fault currently supports only "
            "window=post-commit"
        )

    injector = build_fault_injector(fault)
    fault_description = injector.describe()

    suffix = uuid.uuid4().hex[:8]
    job_id = (
        f"payment-{window}-{mode}-{suffix}"
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    artifact_dir = Path(
        "artifacts/runs"
    ) / (
        f"{stamp}-celery-{window}-{mode}-{suffix}"
    )

    artifact_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    orchestrator_events: list[HistoryEvent] = []

    print()
    print("Faultline")
    print("=========")
    print(f"Adapter:   celery")
    print(f"Mode:      {mode}")
    print(f"Window:    {window}")
    print(f"Job:       {job_id}")
    print()

    print("[1/8] Starting clean Celery/Redis/PostgreSQL environment")
    fresh_environment()

    print("[2/8] Publishing real Celery task")
    submit(
        mode,
        job_id,
        window,
    )

    ready_marker = fault_window_marker(window)

    wait_for_log(
        WORKER_A,
        f"{ready_marker} job={job_id}",
    )

    print(
        "      Worker A reached "
        f"{window} fault window with token 1"
    )

    orchestrator_events.append(
        HistoryEvent(
            ts=now_iso(),
            type="fault_injected",
            job_id=job_id,
            worker="worker-a",
            fencing_token=1,
            details={"fault": fault_description.inject},
        )
    )

    print(f"[3/8] Injecting {fault_description.inject} into Worker A")
    injector.inject(WORKER_A)

    print("[4/8] Waiting for Redis visibility timeout")
    time.sleep(8)
    print("      Redis visibility window expired")

    print("[5/8] Starting Worker B and waiting for redelivery")
    compose(
        "up",
        "-d",
        "worker-b",
        capture=False,
    )

    wait_for_log(
        WORKER_B,
        "ready.",
    )

    worker_b_terminal = worker_b_terminal_marker(
        mode,
        window,
    )

    wait_for_log(
        WORKER_B,
        f"{worker_b_terminal} job={job_id}",
        timeout=45,
    )

    takeover_token = current_token(job_id)

    if worker_b_terminal == "COMMIT_ACCEPTED":
        print(
            "      Worker B redelivered task and "
            f"committed token {takeover_token}"
        )
    else:
        print(
            "      Worker B redelivered task and "
            "suppressed the duplicate effect"
        )

    orchestrator_events.append(
        HistoryEvent(
            ts=now_iso(),
            type="ownership_observed",
            job_id=job_id,
            worker="worker-b",
            fencing_token=takeover_token,
        )
    )

    if fault == "pause":
        print("[6/8] Resuming Worker A")

        orchestrator_events.append(
            HistoryEvent(
                ts=now_iso(),
                type="fault_recovered",
                job_id=job_id,
                worker="worker-a",
                fencing_token=1,
                details={"fault": fault_description.recover},
            )
        )

        injector.recover(WORKER_A)

        expected_terminal = worker_a_terminal_marker(
            mode,
            window,
        )

        wait_for_log(
            WORKER_A,
            f"{expected_terminal} job={job_id}",
            timeout=45,
        )

    else:
        print("[6/8] Restarting Worker A after process crash")

        orchestrator_events.append(
            HistoryEvent(
                ts=now_iso(),
                type="fault_recovered",
                job_id=job_id,
                worker="worker-a",
                fencing_token=1,
                details={"fault": fault_description.recover},
            )
        )

        injector.recover(WORKER_A)

    print("[7/8] Querying PostgreSQL evidence")

    effects = query_effects(job_id)
    rejections = query_rejections(job_id)

    committed_effects = len(effects)

    invariant = at_most_one_effect(committed_effects)
    invariant_pass = invariant.passed

    database_events = parse_attempt_history(job_id)

    duplicate_suppressions = [
        asdict(event)
        for event in database_events
        if event.type == "duplicate_suppressed"
    ]

    all_events = database_events + orchestrator_events

    all_events.sort(
        key=lambda event: datetime.fromisoformat(
            event.ts.replace(" ", "T", 1)
        )
    )

    write_jsonl(
        artifact_dir / "history.jsonl",
        all_events,
    )

    report: dict[str, object] = {
        "framework": "faultline",
        "adapter": "celery",
        "mode": mode,
        "window": window,
        "job_id": job_id,
        "fault": fault,
        "fault_injection": fault_description.as_report(),
        "broker": "Redis",
        "database": "PostgreSQL",
        "invariant": invariant.name,
        "invariant_observed": invariant.observed,
        "invariant_limit": invariant.limit,
        "committed_effects": committed_effects,
        "effects": effects,
        "stale_rejections": rejections,
        "duplicate_suppressions": duplicate_suppressions,
        "current_fencing_token": current_token(job_id),
        "result": "PASS" if invariant_pass else "FAIL",
        "methodology": (
            (
                "Real Celery workers and Redis broker with PostgreSQL "
                "side-effect ledger; Worker A is paused before its "
                "first side-effect commit while the task remains "
                "unacknowledged, forcing Redis redelivery."
            )
            if window == "pre-commit"
            else (
                (
                    "Real Celery workers and Redis broker with PostgreSQL "
                    "side-effect ledger; Worker A commits the side effect "
                    "and is paused before task return/ack, forcing Redis "
                    "to redeliver the already-committed logical job."
                )
                if fault == "pause"
                else (
                    "Real Celery workers and Redis broker with PostgreSQL "
                    "side-effect ledger; Worker A commits the side effect "
                    f"and is killed with {fault_description.inject} "
                    "before task return/ack, "
                    "forcing Redis to redeliver the already-committed "
                    "logical job."
                )
            )
        ),
    }

    (artifact_dir / "report.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )

    (artifact_dir / "worker-a.log").write_text(
        logs(WORKER_A)
    )

    (artifact_dir / "worker-b.log").write_text(
        logs(WORKER_B)
    )

    print("[8/8] Invariant result")
    print()
    print("----------------------------------------")
    print(f"Committed effects:       {committed_effects}")
    print(f"Stale rejections:        {len(rejections)}")
    print(
        f"Duplicate suppressions:  "
        f"{len(duplicate_suppressions)}"
    )
    print(f"Current fencing token:   {report['current_fencing_token']}")
    print("----------------------------------------")
    print(
        f"AT_MOST_ONE_EFFECT: "
        f"{'PASS' if invariant_pass else 'FAIL'}"
    )
    print()
    print(f"History: {artifact_dir / 'history.jsonl'}")
    print(f"Report:  {artifact_dir / 'report.json'}")

    return report, artifact_dir


def run_race(
    mode: str,
    fault: str = "pause",
    window: str = "pre-commit",
) -> tuple[dict[str, object], Path]:
    """Run one Celery experiment with guaranteed best-effort cleanup."""
    if fault == "kill" and window != "post-commit":
        raise RunError(
            "kill fault currently supports only "
            "window=post-commit"
        )

    with build_run_lifecycle(fault):
        return _run_race(
            mode,
            fault=fault,
            window=window,
        )
