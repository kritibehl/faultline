import json

import pytest

import faultline.cleanup_run as module


def make_run(
    tmp_path,
    *,
    project="faultline-celery-abcdef123456",
    audit_status="PASS",
):
    audit = {
        "status": audit_status,
        "job_id": "job-1",
    }

    report = {
        "job_id": "job-1",
        "adapter": "celery",
        "compose_project": project,
        "result": "PASS",
        "recovery_audit": audit,
    }

    (tmp_path / "report.json").write_text(
        json.dumps(report)
    )
    (tmp_path / "recovery-audit.json").write_text(
        json.dumps(audit)
    )
    (tmp_path / "history.jsonl").write_text(
        json.dumps({
            "job_id": "job-1",
            "type": "fault_injected",
        }) + "\n"
    )
    (tmp_path / "worker-a.log").write_text("logs")
    (tmp_path / "worker-b.log").write_text("logs")

    return project


def stub_docker(monkeypatch, project, label_project=None):
    owner = label_project or project

    def fake_output(args, *, text):
        if args[1] == "ps":
            return "cid1\ncid2\n"

        if args[1] == "inspect":
            return json.dumps([
                {
                    "Name": f"/{project}-{service}",
                    "Config": {
                        "Labels": {
                            "com.docker.compose.project": owner,
                            "com.docker.compose.service": service,
                        }
                    },
                }
                for service in ("postgres", "redis")
            ])

        raise AssertionError(args)

    monkeypatch.setattr(
        module.subprocess,
        "check_output",
        fake_output,
    )


def test_dry_run_never_removes_resources(tmp_path, monkeypatch):
    project = make_run(tmp_path)
    stub_docker(monkeypatch, project)

    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected Docker removal")

    monkeypatch.setattr(
        module.subprocess,
        "run",
        forbidden,
    )

    module.cleanup(tmp_path)


def test_apply_targets_only_recorded_project(
    tmp_path, monkeypatch
):
    project = make_run(tmp_path)
    stub_docker(monkeypatch, project)

    calls = []

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda args, **kwargs: calls.append((args, kwargs)),
    )

    module.cleanup(tmp_path, apply=True)

    assert len(calls) == 1
    args, kwargs = calls[0]

    assert args[:4] == [
        "docker", "compose", "-p", project
    ]
    assert args[-2:] == ["down", "--volumes"]
    assert kwargs["check"] is True


def test_rejects_nonisolated_project(tmp_path):
    make_run(tmp_path, project="bullmq")

    with pytest.raises(ValueError, match="project"):
        module.validate_evidence(tmp_path)


def test_rejects_failed_audit(tmp_path):
    make_run(tmp_path, audit_status="FAIL")

    with pytest.raises(ValueError, match="passing"):
        module.validate_evidence(tmp_path)


def test_rejects_missing_artifacts(tmp_path):
    make_run(tmp_path)
    (tmp_path / "worker-b.log").unlink()

    with pytest.raises(ValueError, match="missing preserved"):
        module.validate_evidence(tmp_path)


def test_rejects_foreign_container_owner(
    tmp_path, monkeypatch
):
    project = make_run(tmp_path)

    stub_docker(
        monkeypatch,
        project,
        label_project="vplan",
    )

    with pytest.raises(ValueError, match="unexpected container"):
        module.cleanup(tmp_path, apply=True)
