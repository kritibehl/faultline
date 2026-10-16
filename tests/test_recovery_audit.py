from datetime import datetime, timedelta, timezone

import pytest

from faultline.reporting.recovery_audit import audit_recovery


START = datetime(2026, 10, 16, 3, 23, 19, tzinfo=timezone.utc)
JOB = "payment-test"

REPORT = {
    "job_id": JOB,
    "adapter": "celery",
    "committed_effects": 1,
}


def event(seconds, kind, worker="worker-a", job_id=JOB):
    return {
        "ts": (START + timedelta(seconds=seconds)).isoformat(),
        "type": kind,
        "worker": worker,
        "job_id": job_id,
    }


def baseline():
    return [
        event(-1, "delivery_started"),
        event(0, "fault_injected"),
        event(13, "delivery_started", "worker-b"),
        event(14, "commit_accepted", "worker-b"),
        event(15, "fault_recovered"),
        event(16, "commit_rejected"),
    ]


def test_real_shape_passes():
    result = audit_recovery(REPORT, baseline())
    assert result["status"] == "PASS"
    assert result["elapsed_seconds"] == 14


def test_late_completion_is_failure():
    data = baseline()
    data[3] = event(61, "commit_accepted", "worker-b")
    assert audit_recovery(REPORT, data)["status"] == "FAIL"


def test_short_observation_is_inconclusive():
    data = [
        e for e in baseline()
        if e["type"] != "commit_accepted"
    ]
    assert audit_recovery(REPORT, data)["status"] == "INCONCLUSIVE"


def test_full_deadline_without_terminal_fails():
    data = [
        e for e in baseline()
        if e["type"] != "commit_accepted"
    ]
    data.append(event(61, "observation_completed"))
    assert audit_recovery(REPORT, data)["status"] == "FAIL"


def test_other_jobs_cannot_supply_terminal():
    data = baseline()
    data[3] = event(
        14, "commit_accepted", "worker-b", "other-job"
    )
    assert audit_recovery(REPORT, data)["status"] == "INCONCLUSIVE"


def test_worker_a_is_not_worker_b_recovery():
    data = [
        e for e in baseline()
        if e["type"] != "commit_accepted"
    ]
    data.append(event(17, "commit_accepted", "worker-a"))
    assert audit_recovery(REPORT, data)["status"] == "INCONCLUSIVE"


def test_missing_committed_effect_fails():
    result = audit_recovery(
        {**REPORT, "committed_effects": 0},
        baseline(),
    )
    assert result["status"] == "FAIL"


def test_missing_fault_marker_is_inconclusive():
    data = [
        e for e in baseline()
        if e["type"] != "fault_injected"
    ]
    assert audit_recovery(REPORT, data)["status"] == "INCONCLUSIVE"


def test_suppression_requires_prior_commit():
    data = baseline()
    data[3] = event(
        14, "duplicate_suppressed", "worker-b"
    )
    assert audit_recovery(REPORT, data)["status"] == "INCONCLUSIVE"


def test_valid_suppression_passes():
    data = baseline()
    data.insert(
        1, event(-0.5, "commit_accepted", "worker-a")
    )
    data[4] = event(
        14, "duplicate_suppressed", "worker-b"
    )
    assert audit_recovery(REPORT, data)["status"] == "PASS"


def test_naive_timestamp_is_inconclusive():
    data = baseline()
    data[3]["ts"] = "2026-10-16 03:23:33"
    assert audit_recovery(REPORT, data)["status"] == "INCONCLUSIVE"


def test_invalid_timeout_rejected():
    with pytest.raises(ValueError):
        audit_recovery(
            REPORT, baseline(), timeout_seconds=0
        )
