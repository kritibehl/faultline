"""Scoped cleanup of completed Faultline experiments."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

SERVICES = {
    "postgres",
    "redis",
    "worker-a",
    "worker-b",
}


def validate_evidence(run_dir: Path) -> tuple[str, str]:
    required = (
        "report.json",
        "recovery-audit.json",
        "history.jsonl",
        "worker-a.log",
        "worker-b.log",
    )

    missing = [
        name for name in required
        if not (run_dir / name).is_file()
    ]

    if missing:
        raise ValueError(
            "missing preserved evidence: "
            + ", ".join(missing)
        )

    report: dict[str, Any] = json.loads(
        (run_dir / "report.json").read_text()
    )
    audit: dict[str, Any] = json.loads(
        (run_dir / "recovery-audit.json").read_text()
    )

    adapter = report.get("adapter")
    project = report.get("compose_project")

    if adapter not in ("celery", "bullmq"):
        raise ValueError("unsupported adapter in report")

    if not isinstance(project, str) or not re.fullmatch(
        rf"faultline-{adapter}-[0-9a-f]{{12}}",
        project,
    ):
        raise ValueError(
            "missing or invalid per-run Compose project"
        )

    if (
        report.get("result") != "PASS"
        or audit.get("status") != "PASS"
        or report.get("recovery_audit") != audit
        or report.get("job_id") != audit.get("job_id")
    ):
        raise ValueError(
            "cleanup requires a verified passing report and audit"
        )

    lines = (
        run_dir / "history.jsonl"
    ).read_text().splitlines()

    if not lines or not any(
        json.loads(line).get("job_id") == report["job_id"]
        for line in lines if line.strip()
    ):
        raise ValueError("no matching job history found")

    return adapter, project


def cleanup(run_dir: Path, *, apply: bool = False) -> None:
    adapter, project = validate_evidence(run_dir)

    command = [
        "docker", "compose",
        "-p", project,
        "-f", str(
            ROOT / "integrations" / adapter
            / "docker-compose.yml"
        ),
        "-f", str(
            ROOT / "integrations" / adapter
            / "docker-compose.isolation.yml"
        ),
        "down",
        "--volumes",
    ]

    ids = subprocess.check_output(
        [
            "docker", "ps", "-aq",
            "--filter",
            f"label=com.docker.compose.project={project}",
        ],
        text=True,
    ).split()

    if not ids:
        raise ValueError(
            "no containers found for the recorded project"
        )

    inspected = json.loads(
        subprocess.check_output(
            ["docker", "inspect", *ids],
            text=True,
        )
    )

    found = set()

    for container in inspected:
        labels = (
            container.get("Config", {}).get("Labels")
            or {}
        )

        service = labels.get("com.docker.compose.service")
        owner = labels.get("com.docker.compose.project")

        if owner != project or service not in SERVICES:
            raise ValueError(
                "unexpected container in cleanup scope: "
                + str(container.get("Name"))
            )

        if container.get("Name") != f"/{project}-{service}":
            raise ValueError(
                "unexpected container name: "
                + str(container.get("Name"))
            )

        found.add(service)

    if not {"postgres", "redis"}.issubset(found):
        raise ValueError(
            "missing expected Postgres or Redis container"
        )

    print("Verified project:", project)
    print("Services:", ", ".join(sorted(found)))
    print("Command:", shlex.join(command))

    if apply:
        subprocess.run(
            command,
            check=True,
            cwd=ROOT,
        )
        print(
            "Cleanup complete. Saved experiment "
            "artifacts were preserved."
        )
    else:
        print(
            "DRY RUN: No resources removed. "
            "Use --apply to execute."
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Remove this run's disposable containers and volumes",
    )

    args = parser.parse_args()

    try:
        cleanup(args.run_dir, apply=args.apply)
    except (
        ValueError,
        OSError,
        subprocess.CalledProcessError,
    ) as exc:
        parser.exit(2, f"CLEANUP REFUSED: {exc}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
