from __future__ import annotations

import json
import re
import subprocess
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from faultline.adapters.base import (
    AdapterCapabilities,
    RunError,
)
from faultline.faults.base import FaultInjector
from faultline.faults.process import DockerProcessKillFault
from faultline.history import (
    HistoryEvent,
    now_iso,
    write_jsonl,
)
from faultline.invariants.effects import at_most_one_effect
from faultline.lifecycle import RunLifecycle


COMPOSE = "integrations/bullmq/docker-compose.yml"

WORKER_A = "faultline-bullmq-worker-a"
WORKER_B = "faultline-bullmq-worker-b"
POSTGRES = "faultline-bullmq-postgres"

LOCK_DURATION_MS = 5000
STALLED_INTERVAL_MS = 1000


CAPABILITIES = AdapterCapabilities(
    process_pause=False,
    process_kill=True,
    broker_disconnect=False,
    redelivery=True,
    visibility_expiry=False,
)


def run(
    *args: str,
    capture: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        text=True,
        stdout=(
            subprocess.PIPE
            if capture
            else None
        ),
        stderr=(
            subprocess.STDOUT
            if capture
            else None
        ),
        check=check,
    )


def compose(
    *args: str,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    return run(
        "docker",
        "compose",
        "-f",
        COMPOSE,
        *args,
        capture=capture,
    )


def logs(container: str) -> str:
    result = run(
        "docker",
        "logs",
        container,
        check=False,
    )

    return result.stdout or ""


def wait_for_log(
    container: str,
    needle: str,
    timeout: int = 45,
) -> None:
    import time

    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if needle in logs(container):
            return

        time.sleep(0.5)

    raise RunError(
        f"timed out waiting for "
        f"{needle!r} in {container}"
    )


def log_event_timestamp(
    container: str,
    marker: str,
) -> str:
    for line in logs(container).splitlines():
        if marker not in line:
            continue

        match = re.search(
            r"\bts=([^\s]+)",
            line,
        )

        if match:
            return match.group(1)

    raise RunError(
        f"timestamp missing for "
        f"{marker!r} in {container}"
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


def parse_attempt_history(
    job_id: str,
) -> list[HistoryEvent]:
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
        ts, worker, token, phase = line.split(
            "\t",
            3,
        )

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


def query_effects(
    job_id: str,
) -> list[dict[str, object]]:
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
        worker, token, amount, committed_at = (
            line.split("\t", 3)
        )

        effects.append(
            {
                "worker": worker,
                "fencing_token": int(token),
                "amount": int(amount),
                "committed_at": committed_at,
            }
        )

    return effects


def query_rejections(
    job_id: str,
) -> list[dict[str, object]]:
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
        worker, presented, current, rejected_at = (
            line.split("\t", 3)
        )

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
        "WORKER_READY worker=worker-a",
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


def build_fault_injector(
    fault: str,
) -> FaultInjector:
    if fault == "kill":
        return DockerProcessKillFault(run)

    raise RunError(
        f"BullMQ adapter does not support "
        f"fault={fault!r}"
    )


class BullMQRunLifecycle(RunLifecycle):
    def __init__(self, fault: str) -> None:
        self._injector = build_fault_injector(
            fault
        )

    def cleanup(self) -> None:
        self._injector.recover(
            WORKER_A,
            check=False,
        )


def build_run_lifecycle(
    fault: str,
) -> RunLifecycle:
    return BullMQRunLifecycle(fault)


def validate_configuration(
    mode: str,
    fault: str,
    window: str,
) -> None:
    if mode not in {
        "unsafe",
        "idempotent",
    }:
        raise RunError(
            "BullMQ mode must be "
            "unsafe or idempotent"
        )

    if fault != "kill":
        raise RunError(
            "BullMQ currently supports "
            "only fault=kill"
        )

    if window != "post-commit":
        raise RunError(
            "BullMQ currently supports "
            "only window=post-commit"
        )


def worker_b_terminal_marker(
    mode: str,
) -> str:
    if mode == "unsafe":
        return "COMMIT_ACCEPTED"

    if mode == "idempotent":
        return "DUPLICATE_SUPPRESSED"

    raise RunError(
        f"unsupported BullMQ mode={mode!r}"
    )


def _run_race(
    mode: str,
    fault: str = "kill",
    window: str = "post-commit",
) -> tuple[dict[str, object], Path]:
    validate_configuration(
        mode,
        fault,
        window,
    )

    injector = build_fault_injector(
        fault
    )

    fault_description = injector.describe()

    suffix = uuid.uuid4().hex[:8]

    job_id = (
        f"payment-{window}-{mode}-{suffix}"
    )

    stamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")

    artifact_dir = Path(
        "artifacts/runs"
    ) / (
        f"{stamp}-bullmq-"
        f"{window}-{mode}-{suffix}"
    )

    artifact_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    orchestrator_events: list[
        HistoryEvent
    ] = []

    print()
    print("Faultline")
    print("=========")
    print("Adapter:   bullmq")
    print(f"Mode:      {mode}")
    print(f"Window:    {window}")
    print(f"Job:       {job_id}")
    print()

    print(
        "[1/8] Starting clean "
        "BullMQ/Redis/PostgreSQL environment"
    )

    fresh_environment()

    print(
        "[2/8] Publishing real BullMQ job"
    )

    submit(
        mode,
        job_id,
        window,
    )

    wait_for_log(
        WORKER_A,
        f"READY_AFTER_COMMIT job={job_id}",
    )

    print(
        "      Worker A committed token 1 "
        "and reached post-commit fault window"
    )

    orchestrator_events.append(
        HistoryEvent(
            ts=now_iso(),
            type="fault_injected",
            job_id=job_id,
            worker="worker-a",
            fencing_token=1,
            details={
                "fault":
                    fault_description.inject
            },
        )
    )

    print(
        f"[3/8] Injecting "
        f"{fault_description.inject} "
        "into Worker A"
    )

    injector.inject(WORKER_A)

    print(
        "[4/8] Starting Worker B and "
        "waiting for BullMQ stalled-job recovery"
    )

    compose(
        "up",
        "-d",
        "worker-b",
        capture=False,
    )

    wait_for_log(
        WORKER_B,
        "WORKER_READY worker=worker-b",
    )

    wait_for_log(
        WORKER_B,
        f"JOB_STALLED job={job_id}",
        timeout=45,
    )

    print(
        "      BullMQ detected the expired "
        "job lock and recovered the stalled job"
    )

    stalled_ts = log_event_timestamp(
        WORKER_B,
        f"JOB_STALLED job={job_id}",
    )

    orchestrator_events.append(
        HistoryEvent(
            ts=stalled_ts,
            type="stalled_recovery_observed",
            job_id=job_id,
            worker="worker-b",
            fencing_token=1,
            details={
                "mechanism":
                    "BullMQ stalled-job recovery",
                "semantics":
                    "worker event observation",
            },
        )
    )

    print(
        "[5/8] Waiting for redelivered "
        "job terminal result"
    )

    worker_b_terminal = (
        worker_b_terminal_marker(mode)
    )

    wait_for_log(
        WORKER_B,
        f"{worker_b_terminal} "
        f"job={job_id}",
        timeout=45,
    )

    takeover_token = current_token(
        job_id
    )

    if (
        worker_b_terminal
        == "COMMIT_ACCEPTED"
    ):
        print(
            "      Worker B processed the "
            f"stalled job and committed "
            f"token {takeover_token}"
        )
    else:
        print(
            "      Worker B processed the "
            "stalled job and suppressed "
            "the duplicate effect"
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

    print(
        "[6/8] Restarting Worker A "
        "after process crash"
    )

    orchestrator_events.append(
        HistoryEvent(
            ts=now_iso(),
            type="fault_recovered",
            job_id=job_id,
            worker="worker-a",
            fencing_token=1,
            details={
                "fault":
                    fault_description.recover
            },
        )
    )

    injector.recover(WORKER_A)

    print(
        "[7/8] Querying PostgreSQL evidence"
    )

    effects = query_effects(job_id)
    rejections = query_rejections(job_id)

    committed_effects = len(effects)

    invariant = at_most_one_effect(
        committed_effects
    )

    invariant_pass = invariant.passed

    database_events = (
        parse_attempt_history(job_id)
    )

    duplicate_suppressions = [
        asdict(event)
        for event in database_events
        if (
            event.type
            == "duplicate_suppressed"
        )
    ]

    all_events = (
        database_events
        + orchestrator_events
    )

    all_events.sort(
        key=lambda event:
            datetime.fromisoformat(
                event.ts.replace(
                    " ",
                    "T",
                    1,
                )
            )
    )

    write_jsonl(
        artifact_dir / "history.jsonl",
        all_events,
    )

    report: dict[str, object] = {
        "framework": "faultline",
        "adapter": "bullmq",
        "mode": mode,
        "window": window,
        "job_id": job_id,
        "fault": fault,
        "fault_injection":
            fault_description.as_report(),
        "queue_system": "BullMQ",
        "queue_library_version": "6.3.4",
        "broker": "Redis",
        "database": "PostgreSQL",
        "redelivery_mechanism": (
            "BullMQ stalled-job recovery "
            "after worker-lock expiry"
        ),
        "lock_duration_ms":
            LOCK_DURATION_MS,
        "stalled_interval_ms":
            STALLED_INTERVAL_MS,
        "invariant": invariant.name,
        "invariant_observed":
            invariant.observed,
        "invariant_limit":
            invariant.limit,
        "committed_effects":
            committed_effects,
        "effects": effects,
        "stale_rejections":
            rejections,
        "duplicate_suppressions":
            duplicate_suppressions,
        "current_fencing_token":
            current_token(job_id),
        "result": (
            "PASS"
            if invariant_pass
            else "FAIL"
        ),
        "methodology": (
            "Real BullMQ 6.3.4 workers "
            "with Redis and PostgreSQL; "
            "Worker A commits its side "
            "effect and is killed with "
            f"{fault_description.inject} "
            "before processor return. "
            "After the BullMQ lock expires, "
            "stalled-job recovery makes the "
            "same logical job available for "
            "Worker B."
        ),
    }

    (
        artifact_dir / "report.json"
    ).write_text(
        json.dumps(
            report,
            indent=2,
        )
        + "\n"
    )

    (
        artifact_dir / "worker-a.log"
    ).write_text(
        logs(WORKER_A)
    )

    (
        artifact_dir / "worker-b.log"
    ).write_text(
        logs(WORKER_B)
    )

    print("[8/8] Invariant result")
    print()
    print(
        "----------------------------------------"
    )
    print(
        f"Committed effects:       "
        f"{committed_effects}"
    )
    print(
        f"Stale rejections:        "
        f"{len(rejections)}"
    )
    print(
        f"Duplicate suppressions:  "
        f"{len(duplicate_suppressions)}"
    )
    print(
        f"Current fencing token:   "
        f"{report['current_fencing_token']}"
    )
    print(
        "----------------------------------------"
    )
    print(
        "AT_MOST_ONE_EFFECT: "
        f"{'PASS' if invariant_pass else 'FAIL'}"
    )
    print()
    print(
        f"History: "
        f"{artifact_dir / 'history.jsonl'}"
    )
    print(
        f"Report:  "
        f"{artifact_dir / 'report.json'}"
    )

    return report, artifact_dir


def run_race(
    mode: str,
    fault: str = "kill",
    window: str = "post-commit",
) -> tuple[dict[str, object], Path]:
    validate_configuration(
        mode,
        fault,
        window,
    )

    with build_run_lifecycle(fault):
        return _run_race(
            mode,
            fault=fault,
            window=window,
        )
