from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class HistoryEvent:
    ts: str
    type: str
    job_id: str
    worker: str | None = None
    fencing_token: int | None = None
    details: dict[str, Any] | None = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_jsonl(path: Path, events: list[HistoryEvent]) -> None:
    with path.open("w") as fh:
        for event in events:
            fh.write(json.dumps(asdict(event), sort_keys=True) + "\n")
