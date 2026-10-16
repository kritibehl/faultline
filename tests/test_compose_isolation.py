import subprocess

import pytest

from faultline.adapters import celery, bullmq


@pytest.mark.parametrize("adapter", [celery, bullmq])
def test_compose_uses_isolated_project(monkeypatch, adapter):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout=""
        )

    monkeypatch.setattr(adapter, "run", fake_run)

    adapter.compose("ps", "-q", "worker-a")

    assert len(calls) == 1

    args, _ = calls[0]

    assert args[:4] == (
        "docker", "compose", "-p", adapter.PROJECT_NAME
    )

    assert "-f" in args
    assert adapter.COMPOSE in args
    assert adapter.COMPOSE_OVERRIDE in args

    assert adapter.WORKER_A == (
        f"{adapter.PROJECT_NAME}-worker-a"
    )

    assert adapter.WORKER_B == (
        f"{adapter.PROJECT_NAME}-worker-b"
    )

    assert adapter.POSTGRES == (
        f"{adapter.PROJECT_NAME}-postgres"
    )


def test_adapters_use_different_projects():
    assert celery.PROJECT_NAME != bullmq.PROJECT_NAME
