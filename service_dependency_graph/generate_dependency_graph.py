from __future__ import annotations

import json
from pathlib import Path


GRAPH = {
    "service": "faultline_worker_service",
    "upstream": [
        "producer_api",
        "queue_runtime",
        "retry_scheduler"
    ],
    "downstream": [
        "postgres",
        "outbox",
        "inspector",
        "metrics_exporter"
    ],
    "critical_dependencies": [
        {
            "dependency": "postgres",
            "reason": "fencing-token validation and commit correctness"
        },
        {
            "dependency": "outbox",
            "reason": "replayable event delivery"
        }
    ],
    "failure_blast_radius": {
        "postgres_unavailable": "pause unsafe commits or fail closed",
        "outbox_unavailable": "commit may succeed but delivery must be replayed",
        "metrics_exporter_unavailable": "runtime visibility degraded"
    }
}


def generate() -> dict[str, object]:
    out = Path("service_dependency_graph")
    out.mkdir(parents=True, exist_ok=True)
    (out / "dependency_graph.json").write_text(json.dumps(GRAPH, indent=2))
    return GRAPH


if __name__ == "__main__":
    print(json.dumps(generate(), indent=2))
