from __future__ import annotations

import json
from pathlib import Path


PHASE_ORDER = {
    "claim_job": 1,
    "acquire_lease": 2,
    "execute_job": 3,
    "lease_takeover": 4,
    "commit_result": 5,
    "reject_stale_write": 6,
    "retry_job": 7,
}


def load_events(path: str) -> list[dict]:
    p = Path(path)
    lines = [line for line in p.read_text().splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def reconstruct(events: list[dict]) -> list[dict]:
    return sorted(
        events,
        key=lambda e: (
            e.get("timestamp", ""),
            PHASE_ORDER.get(e.get("phase") or e.get("name"), 99),
        ),
    )


def render_markdown(events: list[dict]) -> str:
    rows = [
        "# Faultline Failure Timeline",
        "",
        "| Step | Phase | Job | Worker | Fencing Token | Timestamp |",
        "|---:|---|---|---|---:|---|",
    ]

    for idx, e in enumerate(events, 1):
        phase = e.get("phase") or e.get("name")
        rows.append(
            f"| {idx} | {phase} | {e.get('job_id', e.get('attributes', {}).get('job_id', ''))} | "
            f"{e.get('worker_id', e.get('attributes', {}).get('worker_id', ''))} | "
            f"{e.get('fencing_token', e.get('attributes', {}).get('fencing_token', ''))} | "
            f"{e.get('timestamp', '')} |"
        )

    rows.append("")
    rows.append("## Interpretation")
    rows.append("")
    rows.append("This timeline reconstructs ownership transitions and shows where stale-worker commits are rejected.")
    return "\n".join(rows) + "\n"


def main() -> None:
    source = Path("docs/dashboard/sample_trace.jsonl")
    if not source.exists():
        raise SystemExit("missing docs/dashboard/sample_trace.jsonl; run scripts/export_trace_demo.py first")

    events = reconstruct(load_events(str(source)))
    out = render_markdown(events)

    Path("docs/timeline").mkdir(parents=True, exist_ok=True)
    Path("docs/timeline/stale_worker_timeline.md").write_text(out)
    print(out)


if __name__ == "__main__":
    main()
