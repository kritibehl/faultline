from faultline.adapters import celery
from faultline.cli import build_parser


def test_pre_commit_fault_marker():
    assert (
        celery.fault_window_marker("pre-commit")
        == "READY_TO_COMMIT"
    )


def test_post_commit_fault_marker():
    assert (
        celery.fault_window_marker("post-commit")
        == "READY_AFTER_COMMIT"
    )


def test_pre_commit_terminal_semantics():
    assert (
        celery.worker_b_terminal_marker(
            "unsafe",
            "pre-commit",
        )
        == "COMMIT_ACCEPTED"
    )

    assert (
        celery.worker_a_terminal_marker(
            "unsafe",
            "pre-commit",
        )
        == "COMMIT_ACCEPTED"
    )

    assert (
        celery.worker_a_terminal_marker(
            "fenced",
            "pre-commit",
        )
        == "COMMIT_REJECTED"
    )

    assert (
        celery.worker_a_terminal_marker(
            "idempotent",
            "pre-commit",
        )
        == "DUPLICATE_SUPPRESSED"
    )


def test_post_commit_terminal_semantics():
    assert (
        celery.worker_b_terminal_marker(
            "unsafe",
            "post-commit",
        )
        == "COMMIT_ACCEPTED"
    )

    assert (
        celery.worker_b_terminal_marker(
            "fenced",
            "post-commit",
        )
        == "COMMIT_ACCEPTED"
    )

    assert (
        celery.worker_b_terminal_marker(
            "idempotent",
            "post-commit",
        )
        == "DUPLICATE_SUPPRESSED"
    )

    assert (
        celery.worker_a_terminal_marker(
            "unsafe",
            "post-commit",
        )
        == "POST_COMMIT_WINDOW_EXIT"
    )


def test_cli_accepts_post_commit_idempotent_run():
    parser = build_parser()

    args = parser.parse_args(
        [
            "test",
            "--adapter",
            "celery",
            "--fault",
            "pause",
            "--window",
            "post-commit",
            "--implementation",
            "idempotent",
            "--invariant",
            "at-most-one-effect",
        ]
    )

    assert args.window == "post-commit"
    assert args.implementation == "idempotent"
