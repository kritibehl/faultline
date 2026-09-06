import pytest

from faultline.adapters import celery
from faultline.cli import build_parser


def test_cli_accepts_post_commit_kill():
    parser = build_parser()

    args = parser.parse_args(
        [
            "test",
            "--adapter",
            "celery",
            "--fault",
            "kill",
            "--window",
            "post-commit",
            "--implementation",
            "unsafe",
            "--invariant",
            "at-most-one-effect",
        ]
    )

    assert args.fault == "kill"
    assert args.window == "post-commit"


def test_kill_rejects_pre_commit_window():
    with pytest.raises(
        celery.RunError,
        match="kill fault currently supports only",
    ):
        celery._run_race(
            "unsafe",
            fault="kill",
            window="pre-commit",
        )


def test_public_kill_pre_commit_rejects_before_lifecycle(monkeypatch):
    lifecycle_calls = []

    def fail_if_built(fault):
        lifecycle_calls.append(fault)
        raise AssertionError(
            "lifecycle must not be built for invalid configuration"
        )

    monkeypatch.setattr(
        celery,
        "build_run_lifecycle",
        fail_if_built,
    )

    with pytest.raises(
        celery.RunError,
        match="kill fault currently supports only",
    ):
        celery.run_race(
            "unsafe",
            fault="kill",
            window="pre-commit",
        )

    assert lifecycle_calls == []
