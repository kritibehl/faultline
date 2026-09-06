from __future__ import annotations

import json
import subprocess
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from faultline.history import HistoryEvent, now_iso, write_jsonl
from faultline.adapters.base import AdapterCapabilities
from faultline.invariants.effects import at_most_one_effect


COMPOSE = "integrations/celery/docker-compose.yml"

WORKER_A = "faultline-celery-worker-a"
WORKER_B = "faultline-celery-worker-b"
POSTGRES = "faultline-celery-postgres"


CAPABILITIES = AdapterCapabilities(
    process_pause=True,
    process_kill=False,
    broker_disconnect=False,
    redelivery=True,
    visibility_expiry=True,
)


class RunError(RuntimeError):
    pass


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


def submit(mode: str, job_id: str) -> None:
    result = compose(
        "run",
        "--rm",
        "client",
        "--mode",
        mode,
        "--job-id",
        job_id,
    )

    if result.stdout:
        print(result.stdout.strip())


def inject_stop(container: str) -> None:
    run(
        "docker",
        "kill",
        "--signal=SIGSTOP",
        container,
    )


def inject_continue(container: str) -> None:
    run(
        "docker",
        "kill",
        "--signal=SIGCONT",
        container,
    )


def best_effort_recover_worker_a() -> None:
    """Never leave the test worker frozen after runner failure."""
    run(
        "docker",
        "kill",
        "--signal=SIGCONT",
        WORKER_A,
        check=False,
    )


def run_race(
    mode: str,
    fault: str = "pause",
) -> tuple[dict[str, object], Path]:
    if mode not in {"unsafe", "fenced"}:
        raise ValueError("mode must be unsafe or fenced")

    if fault != "pause":
        raise ValueError("Celery adapter currently supports only fault=\'pause\'")

    suffix = uuid.uuid4().hex[:8]
    job_id = f"payment-{mode}-{suffix}"

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    artifact_dir = Path(
        "artifacts/runs"
    ) / f"{stamp}-celery-{mode}-{suffix}"

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
    print(f"Job:       {job_id}")
    print()

    print("[1/8] Starting clean Celery/Redis/PostgreSQL environment")
    fresh_environment()

    print("[2/8] Publishing real Celery task")
    submit(mode, job_id)

    wait_for_log(
        WORKER_A,
        f"READY_TO_COMMIT job={job_id}",
    )

    print("      Worker A acquired token 1 and reached commit window")

    orchestrator_events.append(
        HistoryEvent(
            ts=now_iso(),
            type="fault_injected",
            job_id=job_id,
            worker="worker-a",
            fencing_token=1,
            details={"fault": "SIGSTOP"},
        )
    )

    print("[3/8] Injecting SIGSTOP into Worker A")
    inject_stop(WORKER_A)

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

    wait_for_log(
        WORKER_B,
        f"COMMIT_ACCEPTED job={job_id}",
        timeout=45,
    )

    takeover_token = current_token(job_id)

    print(
        f"      Worker B redelivered task and committed token "
        f"{takeover_token}"
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

    print("[6/8] Resuming stale Worker A")

    orchestrator_events.append(
        HistoryEvent(
            ts=now_iso(),
            type="fault_recovered",
            job_id=job_id,
            worker="worker-a",
            fencing_token=1,
            details={"fault": "SIGCONT"},
        )
    )

    inject_continue(WORKER_A)

    expected_terminal = (
        "COMMIT_ACCEPTED"
        if mode == "unsafe"
        else "COMMIT_REJECTED"
    )

    wait_for_log(
        WORKER_A,
        f"{expected_terminal} job={job_id}",
        timeout=45,
    )

    print("[7/8] Querying PostgreSQL evidence")

    effects = query_effects(job_id)
    rejections = query_rejections(job_id)

    committed_effects = len(effects)

    invariant = at_most_one_effect(committed_effects)
    invariant_pass = invariant.passed

    database_events = parse_attempt_history(job_id)

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
        "job_id": job_id,
        "fault": fault,
        "fault_injection": {
            "inject": "SIGSTOP",
            "recover": "SIGCONT",
        },
        "broker": "Redis",
        "database": "PostgreSQL",
        "invariant": invariant.name,
        "invariant_observed": invariant.observed,
        "invariant_limit": invariant.limit,
        "committed_effects": committed_effects,
        "effects": effects,
        "stale_rejections": rejections,
        "current_fencing_token": current_token(job_id),
        "result": "PASS" if invariant_pass else "FAIL",
        "methodology": (
            "Real Celery workers and Redis broker with PostgreSQL "
            "side-effect ledger; worker process is stopped during an "
            "unacknowledged execution window to force redelivery."
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
