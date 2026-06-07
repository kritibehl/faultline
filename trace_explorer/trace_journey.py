from __future__ import annotations

import json
from pathlib import Path


TRACE = {
    "trace_id": "trace-faultline-001",
    "journey": [
        {
            "service": "producer_api",
            "phase": "enqueue_job",
            "span_id": "span-001",
            "duration_ms": 8
        },
        {
            "service": "queue_runtime",
            "phase": "claim_job",
            "span_id": "span-002",
            "duration_ms": 14
        },
        {
            "service": "worker_service",
            "phase": "execute_job",
            "span_id": "span-003",
            "duration_ms": 180
        },
        {
            "service": "postgres",
            "phase": "validate_fencing_token",
            "span_id": "span-004",
            "duration_ms": 12
        },
        {
            "service": "outbox",
            "phase": "write_event",
            "span_id": "span-005",
            "duration_ms": 9
        },
        {
            "service": "inspector",
            "phase": "export_trace",
            "span_id": "span-006",
            "duration_ms": 6
        }
    ],
    "root_cause_signal": {
        "service": "postgres",
        "phase": "validate_fencing_token",
        "decision": "reject_stale_write",
        "submitted_token": 1,
        "current_token": 2
    }
}


def generate_trace_explorer() -> dict[str, object]:
    out = Path("trace_explorer")
    out.mkdir(parents=True, exist_ok=True)

    total_duration = sum(span["duration_ms"] for span in TRACE["journey"])
    services = [span["service"] for span in TRACE["journey"]]

    result = {
        **TRACE,
        "service_path": " -> ".join(services),
        "total_duration_ms": total_duration,
        "span_count": len(TRACE["journey"]),
    }

    (out / "trace_journey.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    print(json.dumps(generate_trace_explorer(), indent=2))
