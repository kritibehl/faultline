from __future__ import annotations

import argparse
import json
import subprocess
import time
import uuid

from dataclasses import asdict
from datetime import (
    datetime,
    timezone,
)
from pathlib import Path

from faultline.adapters.base import (
    RunError,
)
from faultline.faults.process import (
    DockerProcessKillFault,
)
from faultline.history import (
    HistoryEvent,
    now_iso,
    write_jsonl,
)


BASE_COMPOSE = (
    "integrations/celery/"
    "docker-compose.yml"
)

OVERLAY_COMPOSE = (
    "integrations/celery/"
    "docker-compose.ambiguous.yml"
)

WORKER_A = (
    "faultline-celery-worker-a"
)

WORKER_B = (
    "faultline-celery-worker-b"
)

WORKER_POSTGRES = (
    "faultline-celery-postgres"
)

CHARGE_POSTGRES = (
    "faultline-ambiguous-postgres"
)

CHARGE_SERVICE = (
    "faultline-ambiguous-charge-service"
)


STRATEGIES = (
    "naive",
    "fencing",
    "idempotency",
    "fencing-idempotency",
)


VISIBILITY_TIMEOUT_SECONDS = 6

REDELIVERY_WAIT_SECONDS = (
    VISIBILITY_TIMEOUT_SECONDS
    + 2
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


COMPOSE_PROJECT = (
    "faultline-ambiguous"
)


def compose(
    *args: str,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    return run(
        "docker",
        "compose",
        "-p",
        COMPOSE_PROJECT,
        "-f",
        BASE_COMPOSE,
        "-f",
        OVERLAY_COMPOSE,
        *args,
        capture=capture,
    )


def logs(
    container: str,
) -> str:
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
    timeout: int = 60,
) -> None:
    deadline = (
        time.monotonic()
        + timeout
    )

    while (
        time.monotonic()
        < deadline
    ):
        if needle in logs(
            container
        ):
            return

        time.sleep(0.5)

    raise RunError(
        f"timed out waiting for "
        f"{needle!r} in {container}"
    )


def wait_for_log_or_exit(
    container: str,
    needle: str,
    timeout: int = 120,
) -> None:
    deadline = (
        time.monotonic()
        + timeout
    )

    while (
        time.monotonic()
        < deadline
    ):
        current_logs = logs(
            container
        )

        if needle in current_logs:
            return

        state_result = run(
            "docker",
            "inspect",
            "--format",
            "{{.State.Status}}",
            container,
            check=False,
        )

        state = (
            state_result.stdout
            or ""
        ).strip()

        if state in {
            "exited",
            "dead",
        }:
            tail = current_logs[-4000:]

            raise RunError(
                f"{container} exited while "
                f"waiting for {needle!r}\n"
                f"{tail}"
            )

        time.sleep(0.5)

    tail = logs(
        container
    )[-4000:]

    raise RunError(
        f"timed out waiting for "
        f"{needle!r} in {container}\n"
        f"{tail}"
    )


def psql(
    container: str,
    query: str,
) -> str:
    result = run(
        "docker",
        "exec",
        container,
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

    return (
        result.stdout or ""
    ).strip()


def worker_sql(
    query: str,
) -> str:
    return psql(
        WORKER_POSTGRES,
        query,
    )


def charge_sql(
    query: str,
) -> str:
    return psql(
        CHARGE_POSTGRES,
        query,
    )


def parse_worker_history(
    job_id: str,
) -> list[HistoryEvent]:
    output = worker_sql(
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

    events = []

    if not output:
        return events

    for line in output.splitlines():
        (
            ts,
            worker,
            token,
            phase,
        ) = line.split(
            "\t",
            3,
        )

        events.append(
            HistoryEvent(
                ts=ts,
                type=phase,
                job_id=job_id,
                worker=worker,
                fencing_token=int(
                    token
                ),
            )
        )

    return events


def parse_service_history(
    job_id: str,
) -> list[HistoryEvent]:
    output = charge_sql(
        f"""
        SELECT
            created_at,
            COALESCE(
                worker_name,
                ''
            ),
            COALESCE(
                fencing_token::text,
                ''
            ),
            event_type,
            details::text
        FROM service_events
        WHERE job_id = '{job_id}'
        ORDER BY created_at, id;
        """
    )

    events = []

    if not output:
        return events

    for line in output.splitlines():
        (
            ts,
            worker,
            token,
            event_type,
            details,
        ) = line.split(
            "\t",
            4,
        )

        events.append(
            HistoryEvent(
                ts=ts,
                type=event_type,
                job_id=job_id,
                worker=(
                    worker
                    or "charge-service"
                ),
                fencing_token=(
                    int(token)
                    if token
                    else None
                ),
                details=(
                    json.loads(details)
                    if details
                    else None
                ),
            )
        )

    return events


def query_external_effects(
    job_id: str,
) -> list[dict[str, object]]:
    output = charge_sql(
        f"""
        SELECT
            id,
            worker_name,
            fencing_token,
            amount,
            COALESCE(
                idempotency_key,
                ''
            ),
            committed_at
        FROM charges
        WHERE job_id = '{job_id}'
        ORDER BY id;
        """
    )

    effects = []

    if not output:
        return effects

    for line in output.splitlines():
        (
            charge_id,
            worker,
            token,
            amount,
            key,
            committed_at,
        ) = line.split(
            "\t",
            5,
        )

        effects.append(
            {
                "charge_id":
                    int(charge_id),
                "worker":
                    worker,
                "fencing_token":
                    int(token),
                "amount":
                    int(amount),
                "idempotency_key":
                    key or None,
                "committed_at":
                    committed_at,
            }
        )

    return effects


def remote_current_token(
    job_id: str,
) -> int | None:
    value = charge_sql(
        f"""
        SELECT current_token
        FROM remote_ownership
        WHERE job_id = '{job_id}';
        """
    )

    if not value:
        return None

    return int(value)


def current_token(
    job_id: str,
) -> int:
    value = worker_sql(
        f"""
        SELECT current_token
        FROM job_ownership
        WHERE job_id = '{job_id}';
        """
    )

    return int(value)


def submit(
    strategy: str,
    job_id: str,
) -> None:
    result = compose(
        "run",
        "--rm",
        "client",
        "--strategy",
        strategy,
        "--job-id",
        job_id,
    )

    if result.stdout:
        print(
            result.stdout.strip()
        )


def timestamp_key(
    event: HistoryEvent,
) -> datetime:
    raw = event.ts.replace(
        "Z",
        "+00:00",
    )

    parsed = (
        datetime.fromisoformat(
            raw
        )
    )

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed


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
        "charge-postgres",
        "charge-service",
        "worker-a",
        capture=False,
    )

    wait_for_log_or_exit(
        WORKER_A,
        "ready.",
        timeout=180,
    )

    wait_for_log_or_exit(
        CHARGE_SERVICE,
        "CHARGE_SERVICE_READY",
        timeout=180,
    )


def run_strategy(
    strategy: str,
) -> tuple[
    dict[str, object],
    Path,
]:
    if strategy not in STRATEGIES:
        raise RunError(
            f"unsupported strategy: "
            f"{strategy}"
        )

    suffix = (
        uuid.uuid4().hex[:8]
    )

    job_id = (
        f"ambiguous-{strategy}-"
        f"{suffix}"
    )

    print()
    print(
        "Faultline Ambiguous "
        "Remote Outcome"
    )
    print("=" * 34)
    print(
        f"Strategy: {strategy}"
    )
    print(
        f"Job:      {job_id}"
    )
    print()

    print(
        "[1/8] Starting clean "
        "Celery/Redis/worker DB/"
        "charge service"
    )

    fresh_environment()

    print(
        "[2/8] Publishing "
        "real Celery job"
    )

    submit(
        strategy,
        job_id,
    )

    wait_for_log(
        WORKER_A,
        (
            "EFFECT_RESULT_UNKNOWN "
            f"job={job_id}"
        ),
        timeout=60,
    )

    effects_before = (
        query_external_effects(
            job_id
        )
    )

    if len(
        effects_before
    ) != 1:
        raise RunError(
            "caller observed unknown "
            "result but expected exactly "
            "one already-durable remote "
            "effect before redelivery; "
            f"observed="
            f"{len(effects_before)}"
        )

    print(
        "      Worker A observed "
        "UNKNOWN while remote "
        "effect was already durable"
    )

    print(
        "[3/8] SIGKILL Worker A "
        "before task acknowledgement"
    )

    killer = (
        DockerProcessKillFault(
            run
        )
    )

    killer.inject(
        WORKER_A
    )

    fault_event = HistoryEvent(
        ts=now_iso(),
        type="fault_injected",
        job_id=job_id,
        worker="worker-a",
        fencing_token=1,
        details={
            "fault": "SIGKILL",
            "after":
                "effect_result_unknown",
        },
    )

    recovered = False

    try:
        print(
            "[4/8] Waiting for Redis "
            "visibility expiry before "
            "starting Worker B"
        )

        time.sleep(
            REDELIVERY_WAIT_SECONDS
        )

        print(
            "      Visibility window "
            "elapsed; Worker A remains "
            "killed"
        )

        print(
            "      Starting Worker B "
            "for native Celery "
            "redelivery"
        )

        compose(
            "up",
            "-d",
            "worker-b",
            capture=False,
        )

        wait_for_log_or_exit(
            WORKER_B,
            (
                "REMOTE_EFFECT_OBSERVED "
                f"job={job_id}"
            ),
            timeout=120,
        )

        wait_for_log_or_exit(
            WORKER_B,
            (
                "LOCAL_COMMIT_ACCEPTED "
                f"job={job_id}"
            ),
            timeout=30,
        )

        print(
            "      Worker B received "
            "the same logical job"
        )

        print(
            "[5/8] Querying remote "
            "charge ledger"
        )

        external_effects = (
            query_external_effects(
                job_id
            )
        )

        service_history = (
            parse_service_history(
                job_id
            )
        )

        duplicate_suppressions = [
            event
            for event in service_history
            if event.type
            == "duplicate_suppressed"
        ]

        remote_stale_rejections = [
            event
            for event in service_history
            if event.type
            == "stale_remote_rejected"
        ]

        fencing_acceptances = [
            event
            for event in service_history
            if event.type
            == "fencing_accepted"
        ]

        remote_token = (
            remote_current_token(
                job_id
            )
        )

        print(
            "[6/8] Querying worker "
            "ownership state"
        )

        token = current_token(
            job_id
        )

        print(
            "[7/8] Recovering "
            "Worker A container"
        )

        killer.recover(
            WORKER_A,
            check=False,
        )

        recovered = True

        recovery_event = (
            HistoryEvent(
                ts=now_iso(),
                type="fault_recovered",
                job_id=job_id,
                worker="worker-a",
                fencing_token=1,
                details={
                    "fault":
                        "docker start",
                },
            )
        )

    finally:
        if not recovered:
            print(
                "      Worker A remains "
                "killed after failed run; "
                "the next environment "
                "reset will clean it up"
            )

    worker_history = (
        parse_worker_history(
            job_id
        )
    )

    history = (
        worker_history
        + service_history
        + [
            fault_event,
            recovery_event,
        ]
    )

    history.sort(
        key=timestamp_key
    )

    invariant_pass = (
        len(external_effects)
        <= 1
    )

    timestamp = (
        datetime.now(
            timezone.utc
        ).strftime(
            "%Y%m%dT%H%M%SZ"
        )
    )

    artifact_dir = Path(
        "artifacts/runs"
    ) / (
        f"{timestamp}-"
        f"ambiguous-remote-"
        f"{strategy}-"
        f"{suffix}"
    )

    artifact_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    write_jsonl(
        artifact_dir
        / "history.jsonl",
        history,
    )

    report = {
        "framework":
            "faultline",
        "scenario":
            "ambiguous-remote-outcome",
        "adapter":
            "celery",
        "strategy":
            strategy,
        "job_id":
            job_id,
        "fault":
            "remote-response-loss"
            "+SIGKILL",
        "worker_a_observation":
            "effect_result_unknown",
        "effects_before_redelivery":
            len(effects_before),
        "external_effects":
            len(external_effects),
        "external_effect_rows":
            external_effects,
        "duplicate_suppressions":
            len(
                duplicate_suppressions
            ),
        "remote_stale_rejections":
            len(
                remote_stale_rejections
            ),
        "remote_fencing_acceptances":
            len(
                fencing_acceptances
            ),
        "current_fencing_token":
            token,
        "remote_fencing_token":
            remote_token,
        "invariant":
            "at-most-one-logical-effect",
        "result":
            (
                "PASS"
                if invariant_pass
                else "FAIL"
            ),
    }

    (
        artifact_dir
        / "report.json"
    ).write_text(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    print(
        "[8/8] Invariant result"
    )
    print()
    print("-" * 44)
    print(
        "Remote effects before "
        f"redelivery: {len(effects_before)}"
    )
    print(
        "Remote effects after "
        f"redelivery:  {len(external_effects)}"
    )
    print(
        "Duplicate suppressions:    "
        f"{len(duplicate_suppressions)}"
    )
    print(
        "Current ownership token:   "
        f"{token}"
    )
    print(
        "Remote fencing token:      "
        f"{remote_token}"
    )
    print(
        "Remote stale rejections:   "
        f"{len(remote_stale_rejections)}"
    )
    print("-" * 44)
    print(
        "AT_MOST_ONE_LOGICAL_EFFECT: "
        + (
            "PASS"
            if invariant_pass
            else "FAIL"
        )
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

    return (
        report,
        artifact_dir,
    )


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--strategy",
        choices=STRATEGIES,
        required=True,
    )

    args = parser.parse_args()

    try:
        report, _ = run_strategy(
            args.strategy
        )

    except (
        RunError,
        subprocess.CalledProcessError,
        OSError,
    ) as exc:
        print(
            f"FAULTLINE ERROR: {exc}"
        )

        return 2

    return (
        0
        if report["result"]
        == "PASS"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
