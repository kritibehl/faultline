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
