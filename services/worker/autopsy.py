import json
import os
from datetime import datetime

LOG_PATH = os.getenv("AUTOPSY_LOG_PATH", "autopsy.jsonl")


def log_event(event: str, **fields):
    record = {
        "event": event,
        "ts": datetime.utcnow().isoformat(),
        **fields,
    }

    print(json.dumps(record), flush=True)

    try:
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass