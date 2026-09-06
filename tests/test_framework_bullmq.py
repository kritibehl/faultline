import pytest

from faultline.adapters import bullmq
from faultline.adapters.base import RunError
from faultline.cli import build_parser


def test_bullmq_capabilities_are_conservative():
    capabilities = bullmq.CAPABILITIES

    assert capabilities.process_pause is False
    assert capabilities.process_kill is True
    assert capabilities.redelivery is True
    assert capabilities.visibility_expiry is False
    assert capabilities.broker_disconnect is False


def test_cli_accepts_bullmq_crash_run():
    parser = build_parser()

    args = parser.parse_args(
        [
            "test",
            "--adapter",
            "bullmq",
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

    assert args.adapter == "bullmq"
    assert args.fault == "kill"
    assert args.window == "post-commit"
    assert args.implementation == "unsafe"


@pytest.mark.parametrize(
    ("mode", "fault", "window"),
    [
        ("fenced", "kill", "post-commit"),
        ("unsafe", "pause", "post-commit"),
        ("unsafe", "kill", "pre-commit"),
    ],
)
def test_bullmq_rejects_invalid_configuration_before_lifecycle(
    monkeypatch,
    mode,
    fault,
    window,
):
    calls = []

    def fail_if_built(selected_fault):
        calls.append(selected_fault)

        raise AssertionError(
            "lifecycle must not be constructed"
        )

    monkeypatch.setattr(
        bullmq,
        "build_run_lifecycle",
        fail_if_built,
    )

    with pytest.raises(RunError):
        bullmq.run_race(
            mode,
            fault=fault,
            window=window,
        )

    assert calls == []


def test_bullmq_compare_uses_idempotent(
    monkeypatch,
    tmp_path,
):
    import argparse
    import faultline.cli as cli

    calls = []

    reports = {
        "unsafe": {
            "result": "FAIL",
            "committed_effects": 2,
            "duplicate_suppressions": [],
        },
        "idempotent": {
            "result": "PASS",
            "committed_effects": 1,
            "duplicate_suppressions": [
                {"type": "duplicate_suppressed"}
            ],
        },
    }

    def fake_run_race(
        adapter,
        mode,
        *,
        fault,
        window,
    ):
        calls.append(
            (adapter, mode, fault, window)
        )

        directory = tmp_path / mode
        directory.mkdir(
            exist_ok=True
        )

        return reports[mode], directory

    monkeypatch.setattr(
        cli,
        "run_race",
        fake_run_race,
    )

    args = argparse.Namespace(
        adapter="bullmq",
        fault="kill",
        window="post-commit",
        invariant="at-most-one-effect",
    )

    assert cli.run_compare(args) == 0

    assert calls == [
        (
            "bullmq",
            "unsafe",
            "kill",
            "post-commit",
        ),
        (
            "bullmq",
            "idempotent",
            "kill",
            "post-commit",
        ),
    ]


def test_celery_compare_still_uses_fenced(
    monkeypatch,
    tmp_path,
):
    import argparse
    import faultline.cli as cli

    calls = []

    reports = {
        "unsafe": {
            "result": "FAIL",
        },
        "fenced": {
            "result": "PASS",
        },
    }

    def fake_run_race(
        adapter,
        mode,
        *,
        fault,
        window,
    ):
        calls.append(
            (adapter, mode, fault, window)
        )

        directory = tmp_path / mode
        directory.mkdir(
            exist_ok=True
        )

        report_path = (
            directory / "report.json"
        )

        import json

        report_path.write_text(
            json.dumps(
                {
                    "committed_effects": (
                        2
                        if mode == "unsafe"
                        else 1
                    ),
                    "stale_rejections": (
                        []
                        if mode == "unsafe"
                        else [{}]
                    ),
                    "current_fencing_token": 2,
                    "result": reports[mode]["result"],
                }
            )
        )

        return reports[mode], directory

    monkeypatch.setattr(
        cli,
        "run_race",
        fake_run_race,
    )

    args = argparse.Namespace(
        adapter="celery",
        fault="pause",
        window="pre-commit",
        invariant="at-most-one-effect",
    )

    assert cli.run_compare(args) == 0

    assert [
        call[1]
        for call in calls
    ] == [
        "unsafe",
        "fenced",
    ]


def test_stalled_log_timestamp_is_extracted(
    monkeypatch,
):
    timestamp = "2026-09-06T22:28:15.123Z"

    monkeypatch.setattr(
        bullmq,
        "logs",
        lambda container: (
            "WORKER_READY worker=worker-b\n"
            "JOB_STALLED job=payment-42 "
            "worker=worker-b "
            f"ts={timestamp}\n"
        ),
    )

    assert bullmq.log_event_timestamp(
        bullmq.WORKER_B,
        "JOB_STALLED job=payment-42",
    ) == timestamp
