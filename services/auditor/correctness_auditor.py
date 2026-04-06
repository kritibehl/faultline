import json
from pathlib import Path
from collections import defaultdict

ARTIFACT_DIR = Path("artifacts/races")
OUT_DIR = Path("artifacts/reports")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_race_artifacts():
    artifacts = []
    for f in ARTIFACT_DIR.glob("*.json"):
        try:
            artifacts.append(json.loads(f.read_text()))
        except Exception:
            continue
    return artifacts


def analyze(artifacts):
    violations = 0
    near_misses = 0
    heatmap = defaultdict(int)

    details = []

    for a in artifacts:
        job_id = a.get("job_id")
        final_state = a.get("final_state", {})
        token = final_state.get("fencing_token", 0)

        worker_a_log = a.get("worker_a_log", "")
        worker_b_log = a.get("worker_b_log", "")

        # ---- VIOLATION DETECTION ----
        # duplicate commit would show up as multiple "completed" writes
        if "duplicate commit" in worker_a_log or "duplicate commit" in worker_b_log:
            violations += 1
            details.append({"job_id": job_id, "type": "duplicate_commit"})

        # ---- NEAR MISS DETECTION ----
        # stale writer attempted commit but got rejected
        if "stale" in worker_a_log.lower() or "stale" in worker_b_log.lower():
            near_misses += 1
            heatmap["stale_write_attempt"] += 1

        # reclaim race detection
        if token >= 2:
            heatmap["lease_reclaim"] += 1

        # retry contention
        if "retry" in worker_a_log.lower() or "retry" in worker_b_log.lower():
            heatmap["retry_pressure"] += 1

    return {
        "total_runs": len(artifacts),
        "violations_detected": violations,
        "near_miss_races_detected": near_misses,
        "correctness_heatmap": dict(heatmap),
        "details": details,
    }


def write_report(report):
    Path("artifacts/reports/correctness_audit.json").write_text(
        json.dumps(report, indent=2)
    )

    md = f"""# Correctness Audit Report

## Summary
- total runs analyzed: {report['total_runs']}
- violations detected: {report['violations_detected']}
- near-miss races detected: {report['near_miss_races_detected']}

## Heatmap
"""
    for k, v in report["correctness_heatmap"].items():
        md += f"- {k}: {v}\n"

    Path("artifacts/reports/correctness_audit.md").write_text(md)


def main():
    artifacts = load_race_artifacts()
    report = analyze(artifacts)
    write_report(report)
    print("artifacts/reports/correctness_audit.md")


if __name__ == "__main__":
    main()
