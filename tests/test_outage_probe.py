"""Tests for isolated service outages without using Docker or altering other projects."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from faultline import outage_probe as op


def test_namespaced_project():
    assert op.project_name("celery", "abcdef123456") == "faultline-outage-celery-abcdef123456"


@pytest.mark.parametrize("token", ["bad", "0" * 11, "z" * 12, "0" * 13])
def test_reject_unsafe_project_tokens(token):
    with pytest.raises(ValueError):
        op.project_name("celery", token)


@pytest.mark.parametrize("service", ["redis", "postgres"])
def test_probes_only_use_namespaced_network(service):
    p = "faultline-outage-bullmq-abcdef123456"
    args = op.peer_start_args(p, service)
    assert args[:2] == ["docker", "run"]
    assert args[args.index("--network") + 1] == p + "_default"
    assert "--rm" in args
    probes = op.peer_probe_args(p, service)
    assert probes[:2] == ["docker", "exec"]
    assert p + "-probe" in probes
    assert probes[-1] == ("ping" if service == "redis" else "SELECT 1;")


def test_outage_proof_requires_peer_client_timeout():
    assert op.outage_proven({"returncode": 124, "timed_out": False})
    assert not op.outage_proven({"returncode": None, "timed_out": True})
    assert not op.outage_proven({"returncode": 1, "timed_out": False})


def test_reject_arbitrary_network_name():
    with pytest.raises(op.ProbeError):
        op.peer_probe_args("other-workload", "postgres")


def test_compose_uses_both_project_overrides():
    args = op.compose_args("faultline-outage-celery-abcdef123456", "celery", "up", "-d", "redis")
    assert args[:4] == ["docker", "compose", "-p", "faultline-outage-celery-abcdef123456"]
    assert sum(x == "-f" for x in args) == 2
    assert args[-3:] == ["up", "-d", "redis"]
    assert "down" not in args


def test_pause_config_boundaries():
    op.Config("celery", "redis", 4).validate()
    op.Config("bullmq", "postgres", 20).validate()
    for duration in (0, 3.5, 20.1):
        with pytest.raises(ValueError):
            op.Config("celery", "redis", duration).validate()


def test_response_requires_correct_payload():
    assert op.response_ok("redis", {"returncode": 0, "stdout": "PONG\n", "timed_out": False})
    assert op.response_ok("postgres", {"returncode": 0, "stdout": "1\n", "timed_out": False})
    assert not op.response_ok("postgres", {"returncode": 0, "stdout": "PONG", "timed_out": False})
    assert not op.response_ok("redis", {"returncode": 0, "stdout": "PONG", "timed_out": True})
    assert not op.response_ok("redis", {"returncode": 1, "stdout": "PONG", "timed_out": False})


def test_dry_run_does_not_access_disk_or_docker(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(op, "ROOT", tmp_path)
    monkeypatch.setattr(op, "check_space", lambda *_: (_ for _ in ()).throw(AssertionError("disk checked")))
    monkeypatch.setattr(op, "run_command", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("docker invoked")))
    code, path = op.run_probe(op.Config("celery", "redis"), dry_run=True)
    assert code == 0 and path is None
    assert not (tmp_path / "artifacts").exists()
    assert "No Docker, artifacts or Git changes" in capsys.readouterr().out


def test_disk_gate_before_artifact_creation(monkeypatch, tmp_path):
    monkeypatch.setattr(op, "ROOT", tmp_path)
    monkeypatch.setattr(op, "check_space", lambda *_: (_ for _ in ()).throw(op.ProbeError("low disk")))
    with pytest.raises(op.ProbeError, match="low disk"):
        op.run_probe(op.Config("bullmq", "postgres"))
    assert not (tmp_path / "artifacts").exists()


def test_unexpected_container_rejected(monkeypatch):
    project = "faultline-outage-celery-abcdef123456"
    calls = iter([
        {"returncode": 0, "stdout": "123", "timed_out": False},
        {"returncode": 0, "stdout": json.dumps([{
            "Name": "/unrelated", "Config": {"Labels": {
                "com.docker.compose.project": project,
                "com.docker.compose.service": "postgres",
            }}
        }]), "timed_out": False},
    ])
    monkeypatch.setattr(op, "run_command", lambda *_args, **_kwargs: next(calls))
    with pytest.raises(op.ProbeError, match="unexpected container"):
        op.inspect_owned_containers(project, "celery", require_services=True)


def test_missing_service_rejected(monkeypatch):
    project = "faultline-outage-celery-abcdef123456"
    calls = iter([
        {"returncode": 0, "stdout": "123", "timed_out": False},
        {"returncode": 0, "stdout": json.dumps([{
            "Name": f"/{project}-redis", "Config": {"Labels": {
                "com.docker.compose.project": project,
                "com.docker.compose.service": "redis",
            }}
        }]), "timed_out": False},
    ])
    monkeypatch.setattr(op, "run_command", lambda *_args, **_kwargs: next(calls))
    with pytest.raises(op.ProbeError, match="lacks expected"):
        op.inspect_owned_containers(project, "celery", require_services=True)


def test_wait_for_probe_recovers_after_failure(monkeypatch):
    monkeypatch.setattr(op.time, "sleep", lambda *_: None)
    results = iter([
        {"returncode": 1, "stdout": "", "timed_out": False},
        {"returncode": 0, "stdout": "PONG\n", "timed_out": False},
    ])
    ok, attempts = op.wait_for_probe(["fake"], "redis", executor=lambda *_args, **_kw: next(results))
    assert ok and len(attempts) == 2


def _harness(monkeypatch, tmp_path, *, during_available=False, recovery_available=True, cleanup=False, inject_error=False, timeout_code=124, during_timeout_code=None):
    monkeypatch.setattr(op, "ROOT", tmp_path)
    monkeypatch.setattr(op, "check_space", lambda *_: 8.0)
    monkeypatch.setattr(op.time, "sleep", lambda *_: None)
    monkeypatch.setattr(op.uuid, "uuid4", lambda: SimpleNamespace(hex="abcdef1234567890"))
    commands = []
    paused = {"value": False}
    project = "faultline-outage-celery-abcdef123456"
    def fake(args, *, timeout):
        commands.append(list(args))
        if args[:3] == ["docker", "ps", "-aq"]:
            if not any(" up " in " ".join(x) for x in commands):
                return {"returncode": 0, "stdout": "", "timed_out": False}
            return {"returncode": 0, "stdout": "redis123\npg123", "timed_out": False}
        if args[:2] == ["docker", "inspect"] and "--format" not in args:
            return {"returncode": 0, "stdout": json.dumps([
                {"Name": f"/{project}-{service}", "Config": {"Labels": {
                    "com.docker.compose.project": project,
                    "com.docker.compose.service": service,
                }}} for service in ("redis", "postgres")
            ]), "timed_out": False}
        if args[:2] == ["docker", "inspect"]:
            return {"returncode": 0, "stdout": "true" if paused["value"] else "false", "timed_out": False}
        if args[:2] == ["docker", "pause"]:
            if inject_error:
                return {"returncode": 1, "stdout": "", "stderr": "pause refused", "timed_out": False}
            paused["value"] = True
        if args[:2] == ["docker", "unpause"]:
            paused["value"] = False
        if args[:2] == ["docker", "run"]:
            return {"returncode": 0, "stdout": "a" * 64, "stderr": "", "timed_out": False}
        if args[:2] == ["docker", "exec"]:
            if args[-3:] == ["1", "sleep", "4"]:
                return {"returncode": timeout_code, "stdout": "", "stderr": "", "timed_out": False}
            if paused["value"] and not during_available:
                code = during_timeout_code if during_timeout_code is not None else timeout_code
                return {"returncode": code, "stdout": "", "stderr": "", "timed_out": False}
            if not paused["value"] and not recovery_available and any(x[:2] == ["docker", "unpause"] for x in commands):
                return {"returncode": 1, "stdout": "", "stderr": "unavailable", "timed_out": False}
            return {"returncode": 0, "stdout": "PONG", "stderr": "", "timed_out": False}
        return {"returncode": 0, "stdout": "", "stderr": "", "timed_out": False}
    monkeypatch.setattr(op, "run_command", fake)
    return commands, paused, project


def test_realistic_mock_lifecycle_pass(monkeypatch, tmp_path):
    commands, paused, project = _harness(monkeypatch, tmp_path)
    code, path = op.run_probe(op.Config("celery", "redis", cleanup_passing=False))
    report = json.loads(path.read_text())
    assert code == 0 and report["result"] == "PASS"
    assert report["baseline_ready"] and report["outage_observed"] and report["recovered"]
    assert report["cleanup"] == "retained" and not paused["value"]
    assert not any("down" in args for args in commands)
    assert "outages" in str(path)
    assert (path.parent / "compose.log").exists()


def test_unexpected_availability_fails_closed(monkeypatch, tmp_path):
    commands, paused, project = _harness(monkeypatch, tmp_path, during_available=True)
    code, path = op.run_probe(op.Config("celery", "redis"))
    report = json.loads(path.read_text())
    assert code == 2 and report["result"] == "INCONCLUSIVE"
    assert not report["outage_observed"] and not paused["value"]
    assert not any("down" in args for args in commands)


def test_cleanup_pass_only_and_scoped(monkeypatch, tmp_path):
    commands, paused, project = _harness(monkeypatch, tmp_path)
    code, path = op.run_probe(op.Config("celery", "redis", cleanup_passing=True))
    report = json.loads(path.read_text())
    assert code == 0 and report["cleanup"] == "performed_scoped"
    downs = [args for args in commands if "down" in args]
    assert len(downs) == 1
    assert downs[0][downs[0].index("-p") + 1] == project
    assert "--volumes" in downs[0]


def test_inject_failure_retains_environment(monkeypatch, tmp_path):
    commands, paused, project = _harness(monkeypatch, tmp_path, inject_error=True)
    code, path = op.run_probe(op.Config("celery", "redis", cleanup_passing=True))
    report = json.loads(path.read_text())
    assert code == 2 and report["result"] == "INCONCLUSIVE"
    assert "pause refused" in report["error"]
    assert not any("down" in args for args in commands)


def test_cli_invalid_argument_exit_two():
    with pytest.raises(SystemExit) as exc:
        op.main(["--adapter", "celery", "--service", "postgres", "--pause-seconds", "3"])
    assert exc.value.code == 2



def test_busybox_calibrated_timeout(monkeypatch, tmp_path):
    commands, paused, _ = _harness(
        monkeypatch, tmp_path, timeout_code=143
    )
    code, path = op.run_probe(op.Config("celery", "redis"))
    report = json.loads(path.read_text())
    assert code == 0
    assert report["result"] == "PASS"
    assert report["timeout_control_exit_code"] == 143
    assert report["paused_through_probe"] is True
    assert report["outage_observed"] is True
    assert not paused["value"]


def test_mismatched_timeout_not_accepted(monkeypatch, tmp_path):
    commands, paused, _ = _harness(
        monkeypatch, tmp_path,
        timeout_code=124,
        during_timeout_code=143,
    )
    code, path = op.run_probe(
        op.Config("celery", "redis", cleanup_passing=True)
    )
    report = json.loads(path.read_text())
    assert code == 2
    assert report["result"] == "INCONCLUSIVE"
    assert report["timeout_control_exit_code"] == 124
    assert report["outage_observed"] is False
    assert not paused["value"]
    assert not any("down" in cmd for cmd in commands)


def test_invalid_calibration_fails_closed(monkeypatch, tmp_path):
    commands, paused, _ = _harness(
        monkeypatch, tmp_path, timeout_code=0
    )
    code, path = op.run_probe(
        op.Config("celery", "redis", cleanup_passing=True)
    )
    report = json.loads(path.read_text())
    assert code == 2
    assert report["result"] == "INCONCLUSIVE"
    assert "calibration failed" in report["error"]
    assert not paused["value"]
    assert not any(
        cmd[:2] == ["docker", "pause"]
        for cmd in commands
    )
