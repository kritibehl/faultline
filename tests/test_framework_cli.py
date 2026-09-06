from faultline.cli import build_parser


def test_test_command_accepts_public_interface():
    parser = build_parser()

    args = parser.parse_args(
        [
            "test",
            "--adapter",
            "celery",
            "--fault",
            "pause",
            "--implementation",
            "fenced",
            "--invariant",
            "at-most-one-effect",
        ]
    )

    assert args.command == "test"
    assert args.adapter == "celery"
    assert args.fault == "pause"
    assert args.implementation == "fenced"
    assert args.mode is None
    assert args.invariant == "at-most-one-effect"


def test_legacy_mode_remains_supported():
    parser = build_parser()

    args = parser.parse_args(
        [
            "test",
            "--adapter",
            "celery",
            "--mode",
            "unsafe",
        ]
    )

    assert args.mode == "unsafe"
    assert args.implementation is None
    assert args.fault == "pause"


def test_compare_command_accepts_common_arguments():
    parser = build_parser()

    args = parser.parse_args(
        [
            "compare",
            "--adapter",
            "celery",
            "--fault",
            "pause",
            "--invariant",
            "at-most-one-effect",
        ]
    )

    assert args.command == "compare"
    assert args.adapter == "celery"
    assert args.fault == "pause"
    assert args.invariant == "at-most-one-effect"


def test_subprocess_failure_returns_exit_code_2(monkeypatch, capsys):
    import subprocess
    import sys

    import faultline.cli as cli

    def fail_run(*args, **kwargs):
        raise subprocess.CalledProcessError(
            1,
            ["docker", "compose", "down"],
        )

    monkeypatch.setattr(cli, "run_race", fail_run)
    monkeypatch.setattr(
        cli,
        "best_effort_recover_worker_a",
        lambda: None,
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "faultline",
            "test",
            "--adapter",
            "celery",
            "--fault",
            "pause",
            "--implementation",
            "unsafe",
            "--invariant",
            "at-most-one-effect",
        ],
    )

    assert cli.main() == 2

    error = capsys.readouterr().err
    assert "FAULTLINE ERROR" in error
    assert "command failed" in error


def test_missing_runtime_returns_exit_code_2(monkeypatch, capsys):
    import sys

    import faultline.cli as cli

    def fail_run(*args, **kwargs):
        raise FileNotFoundError("docker executable not found")

    monkeypatch.setattr(cli, "run_race", fail_run)
    monkeypatch.setattr(
        cli,
        "best_effort_recover_worker_a",
        lambda: None,
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "faultline",
            "test",
            "--adapter",
            "celery",
            "--fault",
            "pause",
            "--implementation",
            "fenced",
        ],
    )

    assert cli.main() == 2

    error = capsys.readouterr().err
    assert "FAULTLINE ERROR" in error
    assert "infrastructure failure" in error
