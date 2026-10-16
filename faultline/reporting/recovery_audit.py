"""Conservative offline audit of bounded redelivery completion."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


TERMINALS = frozenset({
    "commit_accepted",
    "duplicate_suppressed",
})


def _timestamp(event: dict[str, Any]) -> datetime | None:
    try:
        ts = datetime.fromisoformat(
            str(event["ts"]).replace(" ", "T", 1)
        )
        return ts if ts.tzinfo is not None else None
    except (KeyError, TypeError, ValueError):
        return None


def audit_recovery(
    report: dict[str, Any],
    history: list[dict[str, Any]],
    *,
    timeout_seconds: float = 60,
) -> dict[str, Any]:
    """Audit worker-B terminal evidence after an injected fault."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    job_id = report.get("job_id")

    base = {
        "property": "bounded-redelivery-completion",
        "job_id": job_id,
        "adapter": report.get("adapter"),
        "timeout_seconds": timeout_seconds,
        "status": "INCONCLUSIVE",
        "elapsed_seconds": None,
        "terminal_event": None,
        "reason": "",
        "scope": (
            "Worker B redelivery and durable-effect evidence; "
            "not broker ACK or original-worker completion"
        ),
    }

    def outcome(status, reason, **extra):
        return {
            **base,
            "status": status,
            "reason": reason,
            **extra,
        }

    if not isinstance(job_id, str) or not job_id:
        return outcome("INCONCLUSIVE", "report has no job_id")

    entries = []

    for event in history:
        if not isinstance(event, dict):
            continue
        if event.get("job_id") != job_id:
            continue

        ts = _timestamp(event)
        if ts is None:
            return outcome(
                "INCONCLUSIVE",
                "job history contains a missing or "
                "timezone-naive timestamp",
            )

        entries.append((ts, event))

    entries.sort(key=lambda item: item[0])

    faults = [
        t for t, e in entries
        if e.get("type") == "fault_injected"
    ]

    if len(faults) != 1:
        return outcome(
            "INCONCLUSIVE",
            "expected exactly one fault-injection marker",
        )

    start = faults[0]

    deliveries = [
        t for t, e in entries
        if e.get("type") == "delivery_started"
        and e.get("worker") == "worker-b"
        and t >= start
    ]

    if not deliveries:
        end = entries[-1][0] if entries else start
        elapsed = (end - start).total_seconds()

        return outcome(
            "FAIL" if elapsed >= timeout_seconds
            else "INCONCLUSIVE",
            "no worker-B redelivery observed "
            "within the observation history",
            elapsed_seconds=round(max(0, elapsed), 3),
        )

    delivery = deliveries[0]

    terminal = [
        (t, e) for t, e in entries
        if e.get("type") in TERMINALS
        and e.get("worker") == "worker-b"
        and t >= delivery
    ]

    if not terminal:
        end = entries[-1][0]
        elapsed = (end - start).total_seconds()

        return outcome(
            "FAIL" if elapsed >= timeout_seconds
            else "INCONCLUSIVE",
            "worker B has no terminal durable-effect event",
            elapsed_seconds=round(max(0, elapsed), 3),
        )

    terminal_ts, terminal_event = terminal[0]
    elapsed = (terminal_ts - start).total_seconds()

    common = {
        "elapsed_seconds": round(elapsed, 3),
        "terminal_event": terminal_event["type"],
        "terminal_ts": terminal_ts.isoformat(),
    }

    if elapsed > timeout_seconds:
        return outcome(
            "FAIL",
            "terminal event occurred after deadline",
            **common,
        )

    committed = report.get("committed_effects")

    if not isinstance(committed, int) or committed < 1:
        return outcome(
            "FAIL",
            "no committed effect in PostgreSQL report",
            **common,
        )

    if terminal_event["type"] == "duplicate_suppressed":
        prior_commit = any(
            e.get("type") == "commit_accepted"
            and t <= terminal_ts
            for t, e in entries
        )

        if not prior_commit:
            return outcome(
                "INCONCLUSIVE",
                "suppressed duplicate lacks recorded "
                "prior accepted effect",
                **common,
            )

    return outcome(
        "PASS",
        "redelivered job reached an observed "
        "durable-effect terminal within deadline",
        **common,
    )



def save_recovery_audit(
    report: dict[str, Any],
    history: list[dict[str, Any]],
    run_dir: Path,
    *,
    timeout_seconds: float = 60,
) -> dict[str, Any]:
    """Persist an offline, post-experiment recovery assessment."""

    outcome = audit_recovery(
        report,
        history,
        timeout_seconds=timeout_seconds,
    )

    report["recovery_audit"] = outcome

    for filename, payload in (
        ("recovery-audit.json", outcome),
        ("report.json", report),
    ):
        destination = run_dir / filename
        temporary = run_dir / (filename + ".tmp")

        temporary.write_text(
            json.dumps(payload, indent=2) + chr(10),
            encoding="utf-8",
        )

        temporary.replace(destination)

    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit a completed Faultline run"
    )

    parser.add_argument("run_dir", type=Path)
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=60,
    )

    args = parser.parse_args()
    run_dir = args.run_dir

    report = json.loads(
        (run_dir / "report.json").read_text()
    )

    history = [
        json.loads(line)
        for line in (
            run_dir / "history.jsonl"
        ).read_text().splitlines()
        if line.strip()
    ]

    result = audit_recovery(
        report,
        history,
        timeout_seconds=args.timeout_seconds,
    )

    output = run_dir / "recovery-audit.json"

    output.write_text(
        json.dumps(result, indent=2) + "\n"
    )

    print(json.dumps(result, indent=2))
    print("Audit artifact:", output)

    return {
        "PASS": 0,
        "FAIL": 1,
        "INCONCLUSIVE": 2,
    }[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
