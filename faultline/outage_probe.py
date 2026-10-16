"""Opt-in isolated Redis/PostgreSQL service-outage and recovery probes.

This is a service-level fault experiment, NOT an in-flight worker correctness test.
The probe uses a peer container on the isolated Compose network to validate
baseline response, unavailability during a Docker pause, and restored response.
Never removes a failing/unverified environment or another Compose project.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
ADAPTERS = ("celery", "bullmq")
SERVICES = ("redis", "postgres")
PROBE_TIMEOUT = 3.0
READINESS_TIMEOUT = 90.0


class ProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    adapter: str
    service: str
    pause_seconds: float = 5.0
    min_free_gib: float = 4.0
    cleanup_passing: bool = False

    def validate(self) -> None:
        if self.adapter not in ADAPTERS or self.service not in SERVICES:
            raise ValueError("unsupported adapter or service")
        if not 4 <= self.pause_seconds <= 20:
            raise ValueError("pause_seconds must be between 4 and 20")
        if not 0 <= self.min_free_gib <= 100:
            raise ValueError("min_free_gib must be between 0 and 100")


def project_name(adapter: str, token: str) -> str:
    if adapter not in ADAPTERS or not re.fullmatch(r"[0-9a-f]{12}", token):
        raise ValueError("invalid project identity")
    return f"faultline-outage-{adapter}-{token}"


def validate_project(project: str, adapter: str) -> None:
    if adapter not in ADAPTERS or not re.fullmatch(
        rf"faultline-outage-{adapter}-[0-9a-f]{{12}}", project
    ):
        raise ProbeError("project identity failed allowlist")


def compose_args(project: str, adapter: str, *args: str) -> list[str]:
    validate_project(project, adapter)
    return [
        "docker", "compose", "-p", project,
        "-f", str(ROOT / "integrations" / adapter / "docker-compose.yml"),
        "-f", str(ROOT / "integrations" / adapter / "docker-compose.isolation.yml"),
        *args,
    ]


def peer_name(project: str) -> str:
    if not re.fullmatch(r"faultline-outage-(celery|bullmq)-[0-9a-f]{12}", project):
        raise ProbeError("unsafe project name")
    return project + "-probe"


def peer_start_args(project: str, service: str) -> list[str]:
    """Keep a lightweight peer alive across the entire pause/resume experiment."""
    peer = peer_name(project)
    image = "redis:7-alpine" if service == "redis" else "postgres:15-bookworm"
    if service not in SERVICES:
        raise ValueError("invalid service")
    return [
        "docker", "run", "-d", "--rm", "--network", f"{project}_default",
        "--name", peer, "--label", f"faultline.outage.probe={project}",
        "--entrypoint", "sleep", image, "600",
    ]


def peer_probe_args(project: str, service: str) -> list[str]:
    """Network client runs in the existing peer; client has its own timeout."""
    peer = peer_name(project)
    if service == "redis":
        return [
            "docker", "exec", peer, "timeout", "2",
            "redis-cli", "-h", "redis", "-p", "6379", "ping",
        ]
    if service == "postgres":
        return [
            "docker", "exec", "-e", "PGPASSWORD=faultline", peer,
            "timeout", "2", "psql", "-X", "-v", "ON_ERROR_STOP=1",
            "-A", "-t", "-h", "postgres", "-U", "faultline",
            "-d", "faultline", "-c", "SELECT 1;",
        ]
    raise ValueError("invalid service")


def outage_proven(result: dict[str, Any]) -> bool:
    # 124 is the exit code of the CLIENT timeout inside the running peer;
    # an unrelated Docker CLI timeout/error is not evidence of an outage.
    return result.get("returncode") == 124 and not result.get("timed_out")


def response_ok(service: str, execution: dict[str, Any]) -> bool:
    if execution.get("timed_out") or execution.get("returncode") != 0:
        return False
    output = str(execution.get("stdout", "")).strip().splitlines()
    return bool(output) and output[-1].strip() == ("PONG" if service == "redis" else "1")


def run_command(args: list[str], *, timeout: float) -> dict[str, Any]:
    """Capture result even on failure; cap blocking operations."""
    try:
        proc = subprocess.run(
            args, cwd=ROOT, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=timeout, check=False,
        )
        # Docker inspect produces complete JSON that may exceed 4 KB.
        full_inspect = args[:2] == ["docker", "inspect"] and "--format" not in args
        if full_inspect and len(proc.stdout) > 1_000_000:
            return {
                "returncode": 2,
                "timed_out": False,
                "stdout": "",
                "stderr": "Docker inspect response exceeds 1 MB safety limit",
            }
        return {
            "returncode": proc.returncode,
            "timed_out": False,
            "stdout": proc.stdout if full_inspect else proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": None,
            "timed_out": True,
            "stdout": str(exc.stdout or "")[-4000:],
            "stderr": str(exc.stderr or "")[-4000:],
        }


def require_success(result: dict[str, Any], stage: str) -> None:
    if result.get("returncode") != 0 or result.get("timed_out"):
        raise ProbeError(f"{stage} failed: {result.get('stderr') or result}")


def check_space(min_free_gib: float) -> float:
    free = shutil.disk_usage(ROOT).free / (1024**3)
    if free < min_free_gib:
        raise ProbeError(
            f"low disk space: {free:.2f} GiB < {min_free_gib:.2f} GiB"
        )
    return round(free, 3)


def inspect_owned_containers(
    project: str, adapter: str, *, require_services: bool
) -> list[dict[str, str]]:
    """Fail closed unless every attached container belongs to this project."""
    validate_project(project, adapter)
    ids = run_command([
        "docker", "ps", "-aq", "--filter",
        f"label=com.docker.compose.project={project}",
    ], timeout=20)
    require_success(ids, "listing scoped containers")
    found_ids = ids["stdout"].split()
    if not found_ids:
        if require_services:
            raise ProbeError("isolated project has no containers")
        return []
    inspected = run_command(["docker", "inspect", *found_ids], timeout=25)
    require_success(inspected, "inspecting scoped containers")
    data = json.loads(inspected["stdout"])
    entries: list[dict[str, str]] = []
    for container in data:
        labels = container.get("Config", {}).get("Labels") or {}
        service = labels.get("com.docker.compose.service")
        if (
            labels.get("com.docker.compose.project") != project
            or service not in SERVICES
            or container.get("Name") != f"/{project}-{service}"
        ):
            raise ProbeError("unexpected container in project; refusing cleanup")
        entries.append({"service": service, "name": container["Name"]})
    if require_services and set(x["service"] for x in entries) != set(SERVICES):
        raise ProbeError("isolated project lacks expected service pair")
    return entries


def atomic_report(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def wait_for_probe(
    args: list[str], service: str, *, timeout_seconds: float = READINESS_TIMEOUT,
    executor: Callable[..., dict[str, Any]] | None = None,
) -> tuple[bool, list[dict[str, Any]]]:
    if executor is None:
        executor = run_command
    deadline = time.monotonic() + timeout_seconds
    attempts = []
    while time.monotonic() < deadline:
        remaining = max(0.1, deadline - time.monotonic())
        result = executor(args, timeout=min(5, remaining))
        attempts.append(result)
        if response_ok(service, result):
            return True, attempts
        time.sleep(min(1.0, max(0, deadline - time.monotonic())))
    return False, attempts


def run_probe(config: Config, *, dry_run: bool = False) -> tuple[int, Path | None]:
    config.validate()
    token = uuid.uuid4().hex[:12]
    project = project_name(config.adapter, token)
    probe_args = peer_probe_args(project, config.service)
    compose_start = compose_args(project, config.adapter, "up", "-d", "postgres", "redis")
    if dry_run:
        print("DRY RUN project:", project)
        print("START:", " ".join(compose_start))
        print("PEER:", " ".join(peer_start_args(project, config.service)))
        print("PROBE:", " ".join(probe_args))
        print("INJECT: docker pause", f"{project}-{config.service}")
        print("RECOVER: docker unpause", f"{project}-{config.service}")
        print("No Docker, artifacts or Git changes made.")
        return 0, None

    check_space(config.min_free_gib)
    existing = inspect_owned_containers(project, config.adapter, require_services=False)
    if existing:
        raise ProbeError("random project collision, refusing to reuse")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = ROOT / "artifacts" / "outages" / f"{stamp}-{project}-{config.service}"
    if run_dir.exists():
        raise ProbeError("artifact directory collision")
    run_dir.mkdir(parents=True)
    report_path = run_dir / "report.json"
    record: dict[str, Any] = {
        "framework": "faultline", "experiment": "service-outage-probe",
        "scope": "isolated network-client service availability; not worker-job correctness",
        "adapter": config.adapter, "service": config.service,
        "compose_project": project, "pause_seconds_requested": config.pause_seconds,
        "result": "INCONCLUSIVE", "stage": "environment_setup",
        "baseline_ready": False, "outage_observed": False,
        "recovered": False, "events": [], "cleanup": "retained",
    }
    atomic_report(report_path, record)
    target = f"{project}-{config.service}"
    paused = False
    pause_attempted = False
    restored = False
    started = False
    peer_id: str | None = None
    try:
        print("Starting isolated services:", project, flush=True)
        check_space(config.min_free_gib)
        started = True
        require_success(run_command(compose_start, timeout=360), "starting isolated services")
        inspect_owned_containers(project, config.adapter, require_services=True)
        record["stage"] = "peer_setup"
        peer_result = run_command(peer_start_args(project, config.service), timeout=45)
        require_success(peer_result, "starting service probe peer")
        candidate = peer_result["stdout"].strip()
        if not re.fullmatch(r"[0-9a-f]{64}", candidate):
            raise ProbeError("Docker peer did not return an unambiguous container ID")
        peer_id = candidate
        record["probe_peer_id"] = peer_id
        record["stage"] = "baseline_readiness"
        ok, attempts = wait_for_probe(probe_args, config.service)
        record["events"].append({"stage": "baseline", "ok": ok, "attempts": len(attempts)})
        if not ok:
            raise ProbeError("baseline network probe never reached readiness")
        record["baseline_ready"] = True

        record["stage"] = "injection"
        pause_attempted = True
        require_success(run_command(["docker", "pause", target], timeout=25), "service pause")
        paused = True
        state = run_command(["docker", "inspect", "--format", "{{.State.Paused}}", target], timeout=15)
        require_success(state, "paused-state check")
        if state["stdout"].strip() != "true":
            raise ProbeError("Docker did not confirm paused state")
        begin = time.monotonic()
        record["stage"] = "outage_observation"
        during = run_command(probe_args, timeout=10)
        record["outage_observed"] = outage_proven(during)
        record["events"].append({
            "stage": "during_pause", "probe": during,
            "unavailable": record["outage_observed"],
        })
        time.sleep(max(0.0, config.pause_seconds - (time.monotonic() - begin)))
        record["paused_elapsed_seconds"] = round(time.monotonic() - begin, 3)

        record["stage"] = "service_recovery"
        require_success(run_command(["docker", "unpause", target], timeout=25), "service unpause")
        paused = False
        restored = True
        recovered, after = wait_for_probe(probe_args, config.service)
        record["recovered"] = recovered
        record["events"].append({"stage": "after_unpause", "ok": recovered, "attempts": len(after)})
        record["result"] = (
            "PASS" if record["baseline_ready"] and record["outage_observed"] and recovered
            else "INCONCLUSIVE"
        )
        record["stage"] = "completed"
    except (Exception, KeyboardInterrupt) as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        if isinstance(exc, KeyboardInterrupt):
            record["interrupted"] = True
        print("Outage experiment incomplete:", record["error"], file=sys.stderr)
    finally:
        # Restore the service FIRST, even if peer removal fails.
        if pause_attempted and not restored:
            rescue = run_command(["docker", "unpause", target], timeout=30)
            record["emergency_unpause_attempt"] = rescue
            if rescue.get("returncode") == 0:
                paused = False
                restored = True
        if peer_id is not None:
            try:
                peer_cleanup = run_command(["docker", "rm", "-f", peer_id], timeout=30)
                record["probe_peer_cleanup"] = peer_cleanup
            except (Exception, KeyboardInterrupt) as exc:
                record["probe_peer_cleanup_error"] = repr(exc)
        if started:
            try:
                # Collect only this project's logs without mutating any state.
                logs = run_command(compose_args(project, config.adapter, "logs", "--no-color", "--tail", "100", "postgres", "redis"), timeout=20)
                (run_dir / "compose.log").write_text(logs.get("stdout", "") + logs.get("stderr", ""))
            except (Exception, KeyboardInterrupt) as exc:
                record["log_collection_error"] = repr(exc)
        if pause_attempted and not restored:
            record["result"] = "INCONCLUSIVE"
            record["error"] = "service may still be paused; manual recovery required"
        atomic_report(report_path, record)

    if record["result"] == "PASS" and config.cleanup_passing:
        try:
            inspect_owned_containers(project, config.adapter, require_services=True)
            if not (run_dir / "compose.log").is_file() or not report_path.is_file():
                raise ProbeError("required evidence missing; cleanup refused")
            require_success(run_command(
                compose_args(project, config.adapter, "down", "--volumes"), timeout=180
            ), "scoped cleanup")
            record["cleanup"] = "performed_scoped"
        except (Exception, KeyboardInterrupt) as exc:
            record["cleanup"] = f"failed: {exc}"
        atomic_report(report_path, record)

    print(f"SERVICE OUTAGE {record['result']}: {config.adapter}/{config.service}")
    print("Evidence:", report_path)
    print("Compose project:", project)
    return (0 if record["result"] == "PASS" else 2), report_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", choices=ADAPTERS, required=True)
    parser.add_argument("--service", choices=SERVICES, required=True)
    parser.add_argument("--pause-seconds", type=float, default=5.0)
    parser.add_argument("--min-free-gib", type=float, default=4.0)
    parser.add_argument("--cleanup-passing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    config = Config(args.adapter, args.service, args.pause_seconds, args.min_free_gib, args.cleanup_passing)
    try:
        code, _ = run_probe(config, dry_run=args.dry_run)
        return code
    except (ValueError, ProbeError) as exc:
        parser.exit(2, f"OUTAGE REFUSED: {exc}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
