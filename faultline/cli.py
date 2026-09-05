from __future__ import annotations

import argparse
import json
import sys

from faultline.adapters.celery import (
    RunError,
    best_effort_recover_worker_a,
    run_race,
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
        help="Run a failure-injection correctness test.",
    )

    test.add_argument(
        "--adapter",
        choices=["celery"],
        required=True,
    )

    test.add_argument(
        "--mode",
        choices=["unsafe", "fenced"],
        required=True,
    )

    test.add_argument(
        "--invariant",
        choices=["at-most-one-effect"],
        default="at-most-one-effect",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "test":
            if args.adapter == "celery":
                report, _ = run_race(args.mode)

                return 0 if report["result"] == "PASS" else 1

    except RunError as exc:
        print(f"FAULTLINE ERROR: {exc}", file=sys.stderr)
        return 2

    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130

    finally:
        best_effort_recover_worker_a()

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
