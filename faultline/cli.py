from __future__ import annotations

import argparse
import subprocess
import sys

from faultline.adapters.base import RunError
from faultline.adapters.registry import (
    ADAPTER_NAMES,
    run_race,
)
from faultline.reporting.compare import print_comparison


IMPLEMENTATIONS = (
    "unsafe",
    "fenced",
    "idempotent",
)
FAULTS = (
    "pause",
    "kill",
)
WINDOWS = (
    "pre-commit",
    "post-commit",
)
INVARIANTS = ("at-most-one-effect",)


def add_common_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    parser.add_argument(
        "--adapter",
        choices=ADAPTER_NAMES,
        required=True,
        help="Worker/queue integration to test.",
    )

    parser.add_argument(
        "--fault",
        choices=FAULTS,
        default="pause",
        help="Failure to inject.",
    )

    parser.add_argument(
        "--window",
        choices=WINDOWS,
        default="pre-commit",
        help="Execution window in which to inject the failure.",
    )

    parser.add_argument(
        "--invariant",
        choices=INVARIANTS,
        default="at-most-one-effect",
        help="Correctness property to check.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="faultline",
        description=(
            "Failure testing for at-least-once background workers."
        ),
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    test = subparsers.add_parser(
        "test",
        help="Run one failure-injection correctness test.",
    )

    add_common_arguments(test)

    implementation = test.add_mutually_exclusive_group(
        required=True,
    )

    implementation.add_argument(
        "--implementation",
        choices=IMPLEMENTATIONS,
        help="Implementation under test.",
    )

    implementation.add_argument(
        "--mode",
        choices=IMPLEMENTATIONS,
        help=(
            "Backward-compatible alias for --implementation."
        ),
    )

    compare = subparsers.add_parser(
        "compare",
        help=(
            "Run unsafe and fenced implementations under the "
            "same fault and compare their correctness."
        ),
    )

    add_common_arguments(compare)

    return parser


def run_test(args: argparse.Namespace) -> int:
    implementation = args.implementation or args.mode

    report, _ = run_race(
        args.adapter,
        implementation,
        fault=args.fault,
        window=args.window,
    )

    return 0 if report["result"] == "PASS" else 1


def run_compare(args: argparse.Namespace) -> int:
    print()
    print("Running unsafe implementation...")
    print()

    unsafe_report, unsafe_dir = run_race(
        args.adapter,
        "unsafe",
        fault=args.fault,
        window=args.window,
    )

    second_mode = (
        "idempotent"
        if args.adapter == "bullmq"
        else "fenced"
    )

    print()
    print(
        f"Running {second_mode} implementation..."
    )
    print()

    second_report, second_dir = run_race(
        args.adapter,
        second_mode,
        fault=args.fault,
        window=args.window,
    )

    if args.adapter == "bullmq":
        print("Faultline Correctness Comparison")
        print("================================")
        print()
        print(
            f"{'':28}"
            f"{'UNSAFE':>12}"
            f"{'IDEMPOTENT':>14}"
        )
        print("-" * 54)
        print(
            f"{'Committed effects':28}"
            f"{unsafe_report['committed_effects']:>12}"
            f"{second_report['committed_effects']:>14}"
        )
        print(
            f"{'Duplicate suppressions':28}"
            f"{len(unsafe_report['duplicate_suppressions']):>12}"
            f"{len(second_report['duplicate_suppressions']):>14}"
        )
        print(
            f"{'Invariant':28}"
            f"{unsafe_report['result']:>12}"
            f"{second_report['result']:>14}"
        )
        print()
    else:
        print_comparison(
            unsafe_dir / "report.json",
            second_dir / "report.json",
        )

    print(
        f"Unsafe report: "
        f"{unsafe_dir / 'report.json'}"
    )
    print(
        f"{second_mode.capitalize()} report: "
        f"{second_dir / 'report.json'}"
    )
    print()

    if args.adapter == "bullmq":
        expected_contrast = (
            unsafe_report["result"] == "FAIL"
            and second_report["result"] == "PASS"
        )

        success_message = (
            "unsafe duplicated the logical effect; "
            "idempotency preserved it"
        )

        expected_message = (
            "expected unsafe=FAIL and "
            "idempotent=PASS"
        )

    elif args.window == "pre-commit":
        expected_contrast = (
            unsafe_report["result"] == "FAIL"
            and second_report["result"] == "PASS"
        )

        success_message = (
            "unsafe violated the invariant; "
            "fencing preserved it"
        )

        expected_message = (
            "expected unsafe=FAIL and fenced=PASS"
        )

    else:
        expected_contrast = (
            unsafe_report["result"] == "FAIL"
            and second_report["result"] == "FAIL"
        )

        success_message = (
            "both unsafe and fenced implementations violated "
            "the invariant after post-commit redelivery"
        )

        expected_message = (
            "expected unsafe=FAIL and fenced=FAIL"
        )

    if expected_contrast:
        print(
            "COMPARISON RESULT: PASS "
            f"({success_message})"
        )
        return 0

    print(
        "COMPARISON RESULT: FAIL "
        f"({expected_message})"
    )

    return 1


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "test":
            return run_test(args)

        if args.command == "compare":
            return run_compare(args)

    except RunError as exc:
        print(
            f"FAULTLINE ERROR: {exc}",
            file=sys.stderr,
        )
        return 2

    except subprocess.CalledProcessError as exc:
        command = exc.cmd
        if isinstance(command, (list, tuple)):
            command = " ".join(str(part) for part in command)

        print(
            f"FAULTLINE ERROR: command failed "
            f"(exit {exc.returncode}): {command}",
            file=sys.stderr,
        )
        return 2

    except OSError as exc:
        print(
            f"FAULTLINE ERROR: infrastructure failure: {exc}",
            file=sys.stderr,
        )
        return 2

    except KeyboardInterrupt:
        print(
            "\nInterrupted.",
            file=sys.stderr,
        )
        return 130

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
