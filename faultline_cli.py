from __future__ import annotations

import argparse
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="faultline", description="Faultline CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sim = sub.add_parser("simulate", help="run naive vs protected simulation")
    sim.add_argument("--fault-rate", type=float, default=0.1)
    sim.add_argument("--jobs", type=int, default=200)
    sim.add_argument("--workers", type=int, default=8)

    sub.add_parser("report", help="print latest benchmark report")

    args = parser.parse_args()

    if args.command == "simulate":
        raise SystemExit(
            subprocess.call(
                [
                    sys.executable,
                    "cli/simulate.py",
                    "--fault-rate",
                    str(args.fault_rate),
                    "--jobs",
                    str(args.jobs),
                    "--workers",
                    str(args.workers),
                ]
            )
        )

    if args.command == "report":
        raise SystemExit(subprocess.call([sys.executable, "cli/report.py"]))


if __name__ == "__main__":
    main()
