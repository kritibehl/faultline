"""Reproducible isolated Faultline experiment trials and honest summaries.

Does not alter worker adapters or global Docker resources. Passing Compose
projects may be removed ONLY via the existing guarded cleanup utility, when
explicitly opted in. Failed/inconclusive experiments are always retained.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


@dataclass(frozen=True)
class Scenario:
    adapter: str
    mode: str
    fault: str
    window: str
    invariant: str
    expected: str  # PASS (safe baseline) or FAIL (known-unsafe control)


SCENARIOS = {
    "celery-fenced": Scenario("celery", "fenced", "pause", "pre-commit", "no-lost-committed-effect", "PASS"),
    "bullmq-idempotent": Scenario("bullmq", "idempotent", "kill", "post-commit", "no-lost-committed-effect", "PASS"),
    "celery-unsafe-control": Scenario("celery", "unsafe", "pause", "pre-commit", "at-most-one-effect", "FAIL"),
}


def percentile(values: list[float], fraction: float) -> float | None:
    """Nearest-rank percentile, defined for finite nonnegative values only."""
    if not values:
        return None
    if not 0 < fraction <= 1:
        raise ValueError("fraction must be in (0,1]")
    if any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError("invalid latency")
    ordered = sorted(values)
    return round(ordered[math.ceil(fraction * len(ordered)) - 1], 3)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def classify(scenario: Scenario, exit_code: int, run_dir: Path | None) -> dict[str, Any]:
    """Classify evidence; unknown/missing evidence cannot be a PASS."""
    result: dict[str, Any] = {
        "verdict": "INCONCLUSIVE", "selected_invariant": None,
        "recovery_audit": None, "live_observation": None,
        "ownership_audit": None, "live_elapsed_seconds": None,
        "offline_elapsed_seconds": None, "reason": "no unique run evidence",
    }
    if run_dir is None:
        return result

    failure = _read_json(run_dir / "run-failure.json")
    if failure is not None:
        result["reason"] = f"runner stopped: {failure.get('failure_kind', 'unknown')}"
        return result
    report = _read_json(run_dir / "report.json")
    audit = _read_json(run_dir / "recovery-audit.json")
    if report is None or audit is None:
        result["reason"] = "missing or invalid report/audit"
        return result
    if report.get("adapter") != scenario.adapter or report.get("mode") != scenario.mode or report.get("window") != scenario.window:
        result["reason"] = "report does not match requested scenario"
        return result
    if report.get("invariant") != scenario.invariant:
        result["reason"] = "wrong selected invariant"
        return result
    if report.get("recovery_audit") != audit:
        result["reason"] = "report and durable recovery audit disagree"
        return result
    selected = report.get("result")
    if selected not in ("PASS", "FAIL"):
        result["reason"] = "invalid selected invariant status"
        return result
    result["selected_invariant"] = selected
    result["recovery_audit"] = audit.get("status")
    live = report.get("live_recovery_observation")
    if isinstance(live, dict):
        result["live_observation"] = live.get("status")
        elapsed = live.get("elapsed_seconds")
        if isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool) and math.isfinite(elapsed) and elapsed >= 0:
            result["live_elapsed_seconds"] = float(elapsed)
    elapsed_offline = audit.get("elapsed_seconds")
    if isinstance(elapsed_offline, (int, float)) and not isinstance(elapsed_offline, bool) and math.isfinite(elapsed_offline) and elapsed_offline >= 0:
        result["offline_elapsed_seconds"] = float(elapsed_offline)
    ownership = report.get("ownership_audit")
    if scenario.adapter == "celery":
        result["ownership_audit"] = ownership.get("status") if isinstance(ownership, dict) else "MISSING"

    # Detected safety violations are positive evidence even if the chosen
    # invariant differs from the recovery property. A discovered defect must
    # never be counted as a successful safe baseline.
    if selected == "FAIL" or result["ownership_audit"] == "FAIL":
        if exit_code == 1 and selected == "FAIL":
            result["verdict"] = "DETECTED_FAIL"
            result["reason"] = "selected invariant violated with complete durable evidence"
        else:
            result["reason"] = "safety violation observed; runner status requires review"
        return result

    required_artifacts = ("history.jsonl", "worker-a.log", "worker-b.log")
    if any(not (run_dir / f).is_file() for f in required_artifacts):
        result["reason"] = "incomplete forensic evidence"
        return result
    if exit_code != 0:
        result["reason"] = f"runner exit code {exit_code} contradicts PASS report"
        return result
    if report.get("committed_effects") != 1:
        result["reason"] = "expected exactly one committed effect"
        return result
    if audit.get("status") != "PASS":
        result["reason"] = "retrospective recovery not PASS"
        return result
    if result["ownership_audit"] not in (None, "PASS"):
        result["reason"] = "ownership evidence insufficient"
        return result
    if not isinstance(live, dict) or not (
        live.get("status") == "OBSERVED"
        and live.get("clock") == "monotonic"
        and live.get("within_deadline") is True
        and isinstance(live.get("deadline_seconds"), (int, float))
        and live.get("deadline_seconds") > 0
        and isinstance(live.get("elapsed_seconds"), (int, float))
        and not isinstance(live.get("elapsed_seconds"), bool)
        and math.isfinite(live["elapsed_seconds"])
        and 0 <= live["elapsed_seconds"] <= live["deadline_seconds"]
    ):
        result["reason"] = "monotonic live observation not proven within deadline"
        return result
    result["verdict"] = "VERIFIED_PASS"
    result["reason"] = "invariant, live observation and retrospective audit agree"
    return result


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Denominators include inconclusive and infrastructure-error trials."""
    totals = {"attempted": len(rows), "verified_pass": 0, "detected_fail": 0,
              "inconclusive": 0, "expected_outcomes": 0, "unexpected_outcomes": 0}
    for row in rows:
        verdict = row["verdict"]
        field = {"VERIFIED_PASS": "verified_pass", "DETECTED_FAIL": "detected_fail"}.get(verdict, "inconclusive")
        totals[field] += 1
        if (verdict == "VERIFIED_PASS" and row["expected"] == "PASS") or (
            verdict == "DETECTED_FAIL" and row["expected"] == "FAIL"
        ):
            totals["expected_outcomes"] += 1
        else:
            totals["unexpected_outcomes"] += 1
    passes = [r["live_elapsed_seconds"] for r in rows if r["verdict"] == "VERIFIED_PASS"
              and isinstance(r.get("live_elapsed_seconds"), (float, int))]
    totals["verified_live_latency_samples"] = len(passes)
    totals["verified_live_latency_p50_seconds"] = round(median(passes), 3) if passes else None
    totals["verified_live_latency_p95_seconds"] = percentile(passes, 0.95)
    totals["observed_expected_outcome_rate"] = (
        round(totals["expected_outcomes"] / len(rows), 4) if rows else None
    )
    # Never pool unlike queue systems into a single interpreted tail metric.
    by_case = {}
    for case_name in sorted({row["case"] for row in rows}):
        subset = [row for row in rows if row["case"] == case_name]
        observed = [row["live_elapsed_seconds"] for row in subset
                    if row["verdict"] == "VERIFIED_PASS"
                    and isinstance(row.get("live_elapsed_seconds"), (int, float))]
        by_case[case_name] = {
            "attempted": len(subset),
            "verified_pass": sum(row["verdict"] == "VERIFIED_PASS" for row in subset),
            "detected_fail": sum(row["verdict"] == "DETECTED_FAIL" for row in subset),
            "inconclusive": sum(row["verdict"] == "INCONCLUSIVE" for row in subset),
            "verified_live_latency_samples": len(observed),
            "verified_live_latency_p50_seconds": round(median(observed), 3) if observed else None,
            "verified_live_latency_p95_seconds": percentile(observed, 0.95),
        }
    totals["by_case"] = by_case
    return totals


def atomic_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def discover_new_run(root: Path, scenario: Scenario, before: set[Path]) -> Path | None:
    pattern = f"*-{scenario.adapter}-{scenario.window}-{scenario.mode}-*"
    found = [p for p in root.glob(pattern) if p.is_dir() and p not in before]
    return found[0] if len(found) == 1 else None


def _markdown(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = ["# Faultline experiment batch", "", "Scope: sequential, isolated real worker experiments.",
             "The sample is observational; it is not a production reliability SLO.", "",
             f"- Attempted: {summary['attempted']}",
             f"- Verified safe PASS: {summary['verified_pass']}",
             f"- Detected invariant FAIL (unsafe control or regression): {summary['detected_fail']}",
             f"- Inconclusive / setup / runner failure: {summary['inconclusive']}",
             f"- Expected outcomes: {summary['expected_outcomes']}/{summary['attempted']}",
             f"- Live recovery p50 (only verified PASS runs): {summary['verified_live_latency_p50_seconds']} s",
             f"- Live recovery p95, nearest-rank (only verified PASS runs): {summary['verified_live_latency_p95_seconds']} s",
             "", "The latency distribution excludes failures, which are counted separately.",
             "Live time is from successful fault injection to worker-B terminal-marker observation;",
             "it excludes environment setup, report generation, broker ACK, and unrelated processes.",
             "", "| Case | Trial | Verdict | Live seconds | Evidence |", "|---|---:|---|---:|---|"]
    for r in rows:
        lines.append(f"| {r['case']} | {r['trial']} | {r['verdict']} | {r.get('live_elapsed_seconds')} | {r.get('run_dir') or 'not found'} |")
    return "\n".join(lines) + "\n"


def execute(args: argparse.Namespace) -> int:
    root = Path.cwd()
    if not (root / "pyproject.toml").is_file() or not (root / "faultline").is_dir():
        raise RuntimeError("run from Faultline repository root")
    requested = [v.strip() for v in args.cases.split(",") if v.strip()]
    if not requested or any(v not in SCENARIOS for v in requested) or len(set(requested)) != len(requested):
        raise ValueError(f"cases must be distinct selections from {', '.join(SCENARIOS)}")
    if args.trials < 1 or args.trials > 20:
        raise ValueError("trials per case must be 1..20")
    if args.min_free_gib < 0 or not math.isfinite(args.min_free_gib):
        raise ValueError("min-free-gib must be nonnegative and finite")
    if args.run_timeout_seconds < 1 or args.run_timeout_seconds > 3600:
        raise ValueError("run-timeout-seconds must be 1..3600")

    plan = [(name, i) for name in requested for i in range(1, args.trials + 1)]
    if args.dry_run:
        for name, i in plan:
            s = SCENARIOS[name]
            print(f"DRY RUN {name} #{i}: faultline test --adapter {s.adapter} --implementation {s.mode} "
                  f"--fault {s.fault} --window {s.window} --invariant {s.invariant}")
        print("No Docker, filesystem, or Git changes made.")
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    batch = root / "artifacts" / "benchmarks" / f"{stamp}-{uuid.uuid4().hex[:8]}"
    batch.mkdir(parents=True, exist_ok=False)
    runs_root = root / "artifacts" / "runs"
    rows: list[dict[str, Any]] = []
    manifest: dict[str, Any] = {"schema_version": 1, "created_utc": stamp,
        "cases": requested, "trials_per_case": args.trials,
        "cleanup_passing": args.cleanup_passing, "rows": rows,
        "methodology": "sequential real adapter experiments; complete evidence required for verified PASS"}
    atomic_json(batch / "manifest.json", manifest)
    print(f"Batch evidence: {batch}", flush=True)

    for case_name, number in plan:
        scenario = SCENARIOS[case_name]
        free_gib = shutil.disk_usage(root).free / 1024**3
        if free_gib < args.min_free_gib:
            print(f"STOPPED: free disk {free_gib:.2f} GiB < {args.min_free_gib:g} GiB", flush=True)
            break
        before = {p for p in runs_root.iterdir() if p.is_dir()} if runs_root.is_dir() else set()
        argv = ["faultline", "test", "--adapter", scenario.adapter,
            "--implementation", scenario.mode, "--fault", scenario.fault,
            "--window", scenario.window, "--invariant", scenario.invariant]
        log_path = batch / f"{case_name}-{number:02d}.log"
        print(f"RUNNING: {case_name} trial {number}/{args.trials}", flush=True)
        began = time.monotonic()
        with log_path.open("w", encoding="utf-8") as log:
            try:
                completed = subprocess.run(argv, cwd=root, stdin=subprocess.DEVNULL,
                    stdout=log, stderr=subprocess.STDOUT, timeout=args.run_timeout_seconds,
                    check=False, text=True)
                exit_code = completed.returncode
            except (OSError, subprocess.TimeoutExpired) as exc:
                log.write(f"\nTRIAL RUNNER ERROR: {type(exc).__name__}: {exc}\n")
                exit_code = 2
        elapsed_total = round(time.monotonic() - began, 3)
        run_dir = discover_new_run(runs_root, scenario, before)
        evidence = classify(scenario, exit_code, run_dir)
        row = {"case": case_name, "trial": number, "expected": scenario.expected,
               "exit_code": exit_code, "runner_elapsed_seconds": elapsed_total,
               "run_dir": str(run_dir.relative_to(root)) if run_dir else None,
               "runner_log": str(log_path.relative_to(root)), **evidence}
        rows.append(row)
        atomic_json(batch / "manifest.json", manifest)
        print(f"RESULT: {case_name} #{number}: {row['verdict']} ({row['reason']})", flush=True)

        # Cleanup is exclusively opt-in and is delegated to the existing
        # evidence-validated, project-scoped utility. Never clean failed runs.
        if args.cleanup_passing and row["verdict"] == "VERIFIED_PASS" and run_dir:
            dry = subprocess.run([sys.executable, "-m", "faultline.cleanup_run", str(run_dir)],
                cwd=root, capture_output=True, text=True, stdin=subprocess.DEVNULL)
            if dry.returncode == 0 and "DRY RUN" in dry.stdout:
                applied = subprocess.run([sys.executable, "-m", "faultline.cleanup_run",
                    str(run_dir), "--apply"], cwd=root, capture_output=True,
                    text=True, stdin=subprocess.DEVNULL)
                row["cleanup_result"] = "CLEANED" if applied.returncode == 0 else "FAILED"
                row["cleanup_output"] = (applied.stdout + applied.stderr)[-3000:]
            else:
                row["cleanup_result"] = "REFUSED"
            atomic_json(batch / "manifest.json", manifest)

    stats = summarize(rows)
    stats["planned"] = len(plan)
    stats["skipped"] = len(plan) - len(rows)
    stats["completed_all_planned"] = len(rows) == len(plan)
    atomic_json(batch / "summary.json", stats)
    (batch / "SUMMARY.md").write_text(_markdown(stats, rows), encoding="utf-8")
    print("SUMMARY:", json.dumps(stats, sort_keys=True), flush=True)
    print("Report:", batch / "SUMMARY.md", flush=True)
    return 0 if stats["completed_all_planned"] and stats["unexpected_outcomes"] == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute and summarize isolated Faultline trials")
    parser.add_argument("--cases", default="celery-fenced,bullmq-idempotent")
    parser.add_argument("--trials", type=int, default=1, help="trials per case")
    parser.add_argument("--min-free-gib", type=float, default=4.0,
                        help="stop before launching a trial if free disk is below threshold")
    parser.add_argument("--run-timeout-seconds", type=int, default=900,
                        help="total subprocess cap including Docker setup; not recovery observation budget")
    parser.add_argument("--cleanup-passing", action="store_true",
                        help="run the existing scoped cleanup on verified passing projects only")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        return execute(args)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"FAULTLINE TRIALS ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
