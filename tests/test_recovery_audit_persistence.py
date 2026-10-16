import json
from datetime import datetime, timedelta, timezone

import pytest

from faultline.reporting.recovery_audit import save_recovery_audit


START = datetime(
    2026, 10, 16, 3, 23, 19, tzinfo=timezone.utc
)


def event(seconds, kind, worker):
    return {
        "ts": (
            START + timedelta(seconds=seconds)
        ).isoformat(),
        "job_id": "payment-test",
        "type": kind,
        "worker": worker,
    }


@pytest.mark.parametrize(
    ("terminal_second", "expected"),
    [
        (14, "PASS"),
        (61, "FAIL"),
        (None, "INCONCLUSIVE"),
    ],
)
def test_recovery_audit_persistence(
    tmp_path, terminal_second, expected
):
    report = {
        "job_id": "payment-test",
        "adapter": "celery",
        "committed_effects": 1,
        "result": "PASS",
    }

    history = [
        event(0, "fault_injected", "worker-a"),
        event(13, "delivery_started", "worker-b"),
        event(15, "fault_recovered", "worker-a"),
    ]

    if terminal_second is not None:
        history.append(
            event(
                terminal_second,
                "commit_accepted",
                "worker-b",
            )
        )

    result = save_recovery_audit(
        report,
        history,
        tmp_path,
        timeout_seconds=60,
    )

    saved_audit = json.loads(
        (tmp_path / "recovery-audit.json").read_text()
    )

    saved_report = json.loads(
        (tmp_path / "report.json").read_text()
    )

    assert result["status"] == expected
    assert saved_audit == result
    assert saved_report["recovery_audit"] == result

    # Recovery auditing must not silently replace the
    # separately selected effect invariant result.
    assert saved_report["result"] == "PASS"
