import json
import subprocess
from dataclasses import dataclass

import pytest

from faultline.adapters import bullmq, celery
from faultline.reporting import failure_artifacts as evidence


@dataclass
class Event:
    ts: str
    type: str
    job_id: str = "payment-test"
    worker: str = "worker-a"


def kwargs(tmp_path, **changes):
    values = dict(
        run_dir=tmp_path,
        adapter="celery",
        compose_project="faultline-celery-aabbccddeeff",
        job_id="payment-test",
        mode="fenced",
        fault="pause",
        window="pre-commit",
        invariant="no-lost-committed-effect",
        stage="redelivery_observation",
        error=TimeoutError("timed out waiting for COMMIT_ACCEPTED"),
        orchestrator_events=[Event("2026-10-16T03:00:00+00:00", "fault_injected")],
        load_db_events=lambda: [Event("2026-10-16T03:00:01+00:00", "delivery_started")],
        worker_logs={"worker-a": lambda: "A log", "worker-b": lambda: "B log"},
    )
    values.update(changes)
    return values


def test_timeout_is_inconclusive_and_evidence_survives(tmp_path):
    result = evidence.write_failure_evidence(**kwargs(tmp_path))
    assert result["run_status"] == "ERROR"
    assert result["failure_kind"] == "OBSERVATION_TIMEOUT"
    assert result["invariant_result"] == "INCONCLUSIVE"
    assert result["recovery_result"] == "INCONCLUSIVE"
    assert result["stage"] == "redelivery_observation"
    assert result["database_history_status"] == "COLLECTED"
    assert result["compose_project"] == "faultline-celery-aabbccddeeff"
    assert json.loads((tmp_path / "run-failure.json").read_text()) == result
    assert (tmp_path / "worker-a.log").read_text() == "A log"
    assert (tmp_path / "worker-b.log").read_text() == "B log"
    events = [json.loads(line) for line in (tmp_path / "history.jsonl").read_text().splitlines()]
    assert {e["type"] for e in events} == {"fault_injected", "delivery_started", "runner_failed"}
    assert not (tmp_path / "report.json").exists()


def test_partial_evidence_survives_missing_database_and_logs(tmp_path):
    def fail():
        raise OSError("database unavailable")
    result = evidence.write_failure_evidence(**kwargs(
        tmp_path, load_db_events=fail, worker_logs={"worker-a": fail, "worker-b": lambda: ""}
    ))
    assert result["database_history_status"] == "UNAVAILABLE"
    assert "database_history" in result["collection_errors"]
    assert "worker-a_logs" in result["collection_errors"]
    assert result["worker_log_status"]["worker-a"] == "UNAVAILABLE"
    assert (tmp_path / "history.jsonl").is_file()
    assert (tmp_path / "run-failure.json").is_file()


def test_setup_failure_skips_database_query(tmp_path):
    def fail():
        raise AssertionError("should not query database during setup failure")
    result = evidence.write_failure_evidence(**kwargs(tmp_path, stage="environment_setup", load_db_events=fail))
    assert result["database_history_status"] == "NOT_ATTEMPTED"
    assert not result["collection_errors"]


def test_context_manager_preserves_original_error(tmp_path):
    args = kwargs(tmp_path)
    args["stage"] = {"name": args["stage"]}
    args.pop("error")
    with pytest.raises(TimeoutError, match="COMMIT_ACCEPTED"):
        with evidence.preserve_failed_run(**args):
            raise TimeoutError("timed out waiting for COMMIT_ACCEPTED")
    assert (tmp_path / "run-failure.json").is_file()


def test_context_manager_does_not_mask_original_on_capture_error(tmp_path, monkeypatch):
    def fail(**_kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(evidence, "write_failure_evidence", fail)
    args = kwargs(tmp_path)
    args["stage"] = {"name": args["stage"]}
    args.pop("error")
    with pytest.raises(TimeoutError, match="original timeout"):
        with evidence.preserve_failed_run(**args):
            raise TimeoutError("original timeout")


@pytest.mark.parametrize("adapter", [celery, bullmq])
def test_docker_subprocess_cannot_consume_parent_stdin(monkeypatch, adapter):
    recorded = []
    def fake_run(*args, **kwargs):
        recorded.append(kwargs)
        return subprocess.CompletedProcess(args[0], 0, stdout="")
    monkeypatch.setattr(adapter.subprocess, "run", fake_run)
    adapter.run("docker", "ps")
    assert recorded[0]["stdin"] == subprocess.DEVNULL


@pytest.mark.parametrize("adapter,mode,fault,window", [
    (celery, "fenced", "pause", "pre-commit"),
    (bullmq, "idempotent", "kill", "post-commit"),
])
def test_real_adapter_setup_timeout_writes_failure_artifacts(
    tmp_path, monkeypatch, adapter, mode, fault, window
):
    monkeypatch.chdir(tmp_path)
    class Description:
        inject = "SIGSTOP"
    class Injector:
        def describe(self):
            return Description()
    monkeypatch.setattr(adapter, "build_fault_injector", lambda fault: Injector())
    def fail():
        raise adapter.RunError("timed out waiting for worker readiness")
    monkeypatch.setattr(adapter, "fresh_environment", fail)
    monkeypatch.setattr(adapter, "logs", lambda _worker: "")
    monkeypatch.setattr(adapter, "parse_attempt_history", lambda _job: [])
    with pytest.raises(adapter.RunError, match="timed out"):
        adapter._run_race(mode, fault=fault, window=window)
    run_dirs = list((tmp_path / "artifacts" / "runs").iterdir())
    assert len(run_dirs) == 1
    result = json.loads((run_dirs[0] / "run-failure.json").read_text())
    assert result["stage"] == "environment_setup"
    assert result["invariant_result"] == "INCONCLUSIVE"
    assert result["failure_kind"] == "OBSERVATION_TIMEOUT"
    assert (run_dirs[0] / "history.jsonl").is_file()
    assert result["database_history_status"] == "NOT_ATTEMPTED"


def test_lifecycle_cannot_mask_original_failure(capsys):
    from faultline.lifecycle import RunLifecycle

    class FaultyCleanup(RunLifecycle):
        def cleanup(self):
            raise OSError("Docker daemon unavailable")

    with pytest.raises(TimeoutError, match="original failure"):
        with FaultyCleanup():
            raise TimeoutError("original failure")

    assert "recovery cleanup failed" in capsys.readouterr().err


def test_lifecycle_fails_on_cleanup_error_after_success():
    from faultline.lifecycle import RunLifecycle

    class FaultyCleanup(RunLifecycle):
        def cleanup(self):
            raise OSError("cleanup failed")

    with pytest.raises(OSError, match="cleanup failed"):
        with FaultyCleanup():
            pass


@pytest.mark.parametrize("adapter,mode,fault,window", [
    (celery, "fenced", "pause", "pre-commit"),
    (bullmq, "idempotent", "kill", "post-commit"),
])
def test_failed_injection_does_not_claim_fault_was_injected(
    tmp_path, monkeypatch, adapter, mode, fault, window
):
    monkeypatch.chdir(tmp_path)

    class Description:
        inject = "test-fault"

    class Injector:
        def describe(self):
            return Description()

        def inject(self, _worker):
            raise adapter.RunError("injection failed")

    monkeypatch.setattr(adapter, "build_fault_injector", lambda _fault: Injector())
    monkeypatch.setattr(adapter, "fresh_environment", lambda: None)
    monkeypatch.setattr(adapter, "submit", lambda *args: None)
    monkeypatch.setattr(adapter, "wait_for_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(adapter, "logs", lambda _worker: "worker-started")
    monkeypatch.setattr(adapter, "parse_attempt_history", lambda _job: [])
    if adapter is celery:
        monkeypatch.setattr(adapter, "fault_window_marker", lambda _window: "READY")

    with pytest.raises(adapter.RunError, match="injection failed"):
        adapter._run_race(mode, fault=fault, window=window)

    run_dir, = (tmp_path / "artifacts" / "runs").iterdir()
    result = json.loads((run_dir / "run-failure.json").read_text())
    history = [json.loads(line) for line in (run_dir / "history.jsonl").read_text().splitlines()]
    assert result["stage"] == "fault_injection"
    assert result["run_status"] == "ERROR"
    assert "fault_injected" not in [entry["type"] for entry in history]
