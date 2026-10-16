"""Milestone 9 monotonic deadline and cross-adapter regression checks."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from faultline import recovery_deadline as d
from faultline.adapters import celery, bullmq
from faultline.reporting.failure_artifacts import write_failure_evidence


class Clock:
    def __init__(self):
        self.t = 100.0

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(d.time, "monotonic", c.now)
    monkeypatch.setattr(d.time, "sleep", c.sleep)
    return c


def test_valid_observation_uses_monotonic_elapsed(clock):
    with d.recovery_observation_deadline(5) as obs:
        d.bounded_sleep(2)
    result = obs.as_report()
    assert result["status"] == "OBSERVED"
    assert result["elapsed_seconds"] == 2.0
    assert result["within_deadline"] is True


def test_sleep_cannot_overshoot_budget(clock):
    with pytest.raises(d.RecoveryDeadlineExceeded):
        with d.recovery_observation_deadline(3):
            d.bounded_sleep(20)
    assert clock.t == 103.0
    assert d.current_observation() is None


def test_cumulative_budget_not_reset_by_multiple_waits(clock):
    with pytest.raises(d.RecoveryDeadlineExceeded):
        with d.recovery_observation_deadline(4):
            d.bounded_sleep(2.5)
            d.bounded_sleep(2.5)
    assert clock.t == 104.0


@pytest.mark.parametrize("seconds", [0, -1, float("nan"), float("inf"), True])
def test_invalid_deadlines_rejected(seconds):
    with pytest.raises(ValueError):
        with d.recovery_observation_deadline(seconds):
            pass


def test_deadline_context_does_not_leak(clock):
    with pytest.raises(RuntimeError, match="nested"):
        with d.recovery_observation_deadline(5):
            with d.recovery_observation_deadline(2):
                pass
    assert d.current_observation() is None
    d.bounded_sleep(4)
    assert clock.t == 104.0


def test_subprocess_receives_remaining_timeout(monkeypatch, clock):
    calls = []
    def fake(*args, **kwargs):
        calls.append(kwargs)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="")
    monkeypatch.setattr(d.subprocess, "run", fake)
    with d.recovery_observation_deadline(10):
        d.bounded_sleep(3)
        d.bounded_subprocess_run(["docker", "ps"], stdin=subprocess.DEVNULL)
        d.bounded_sleep(4)
        d.bounded_subprocess_run(["docker", "ps"], stdin=subprocess.DEVNULL)
    assert calls[0]["timeout"] == 7
    assert calls[1]["timeout"] == 3


def test_no_active_deadline_does_not_add_timeout(monkeypatch):
    calls = []
    def fake(*args, **kwargs):
        calls.append(kwargs)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="")
    monkeypatch.setattr(d.subprocess, "run", fake)
    d.bounded_subprocess_run(["docker", "ps"])
    assert "timeout" not in calls[0]


def test_preserves_tighter_subprocess_timeout(monkeypatch, clock):
    observed = []
    def fake(*args, **kwargs):
        observed.append(kwargs["timeout"])
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="")
    monkeypatch.setattr(d.subprocess, "run", fake)
    with d.recovery_observation_deadline(10):
        d.bounded_subprocess_run(["docker", "ps"], timeout=2)
    assert observed == [2]


def test_subprocess_timeout_is_observation_error(monkeypatch, clock):
    def fake(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="docker ps", timeout=kwargs["timeout"])
    monkeypatch.setattr(d.subprocess, "run", fake)
    with pytest.raises(d.RecoveryDeadlineExceeded, match="subprocess"):
        with d.recovery_observation_deadline(1):
            d.bounded_subprocess_run(["docker", "ps"])


@pytest.mark.parametrize("adapter", [celery, bullmq])
def test_adapter_subprocess_uses_deadline_without_changing_callers(monkeypatch, clock, adapter):
    observed = []
    def fake(*args, **kwargs):
        observed.append(kwargs.get("timeout"))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="")
    monkeypatch.setattr(d.subprocess, "run", fake)
    with d.recovery_observation_deadline(6):
        adapter.run("docker", "ps")
    assert observed == [6]


@pytest.mark.parametrize("adapter", [celery, bullmq])
def test_wait_for_log_shares_budget_across_calls(monkeypatch, clock, adapter):
    monkeypatch.setattr(adapter, "logs", lambda _: "")
    with pytest.raises(d.RecoveryDeadlineExceeded):
        with d.recovery_observation_deadline(3):
            # Each of these has a 45-second local timeout, but a single
            # three-second global observation window still wins.
            adapter.wait_for_log("worker-b", "never", timeout=45)
    assert clock.t == 103.0


def test_deadline_error_is_runerror_and_timeout():
    err = d.RecoveryDeadlineExceeded("deadline exceeded")
    assert isinstance(err, celery.RunError)
    assert isinstance(err, TimeoutError)


def test_deadline_timeout_preserved_as_inconclusive(tmp_path):
    result = write_failure_evidence(
        run_dir=tmp_path,
        adapter="celery", compose_project="faultline-celery-abcdef123456",
        job_id="payment-test", mode="fenced", fault="pause",
        window="pre-commit", invariant="no-lost-committed-effect",
        stage="redelivery_observation",
        error=d.RecoveryDeadlineExceeded("recovery observation deadline exceeded"),
        orchestrator_events=[], load_db_events=lambda: [],
        worker_logs={"worker-a": lambda: "", "worker-b": lambda: ""},
    )
    assert result["failure_kind"] == "OBSERVATION_TIMEOUT"
    assert result["invariant_result"] == "INCONCLUSIVE"
    assert result["recovery_result"] == "INCONCLUSIVE"
    assert (tmp_path / "run-failure.json").is_file()
    assert not (tmp_path / "report.json").exists()
