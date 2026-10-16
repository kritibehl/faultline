import json
import subprocess

from faultline import outage_probe as op


def test_long_docker_inspect_json(monkeypatch):
    project = "faultline-outage-celery-abcdef123456"

    payload = json.dumps([
        {
            "Name": f"/{project}-{service}",
            "Config": {"Labels": {
                "com.docker.compose.project": project,
                "com.docker.compose.service": service,
                "padding": "x" * 6000,
            }},
        }
        for service in ("postgres", "redis")
    ])

    assert len(payload) > 4000

    def fake_run(args, **kwargs):
        if args[:2] == ["docker", "ps"]:
            return subprocess.CompletedProcess(
                args, 0, "pg-id\\nredis-id\\n", ""
            )
        if args[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(
                args, 0, payload, ""
            )
        raise AssertionError(args)

    monkeypatch.setattr(op.subprocess, "run", fake_run)

    found = op.inspect_owned_containers(
        project, "celery", require_services=True
    )

    assert {x["service"] for x in found} == {
        "postgres", "redis"
    }


def test_oversized_inspect_fails_closed(monkeypatch):
    monkeypatch.setattr(
        op.subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(
            args, 0, "x" * 1_000_001, ""
        ),
    )

    result = op.run_command(
        ["docker", "inspect", "id"], timeout=2
    )

    assert result["returncode"] != 0
    assert "1 MB" in result["stderr"]
    assert not result["stdout"]


def test_regular_output_still_bounded(monkeypatch):
    monkeypatch.setattr(
        op.subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(
            args, 0, "x" * 6000, ""
        ),
    )

    result = op.run_command(
        ["docker", "logs", "example"], timeout=2
    )

    assert len(result["stdout"]) == 4000
