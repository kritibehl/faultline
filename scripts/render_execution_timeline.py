import json
import sys
from pathlib import Path

if len(sys.argv) != 2:
    print("usage: python3 scripts/render_execution_timeline.py <artifact.json>")
    raise SystemExit(1)

path = Path(sys.argv[1])
data = json.loads(path.read_text())

print("\n=== EXECUTION TIMELINE ===\n")

if "timeline" in data:
    for i, ev in enumerate(data["timeline"], start=1):
        print(f"{i}. {ev.get('event')} -> {ev.get('meta', {})}")
else:
    worker_a = data.get("worker_a_log", "")
    worker_b = data.get("worker_b_log", "")
    i = 1
    for actor, text in [("worker-a", worker_a), ("worker-b", worker_b)]:
        for line in text.splitlines():
            print(f"{i}. {actor} -> {line}")
            i += 1

print("\n==========================\n")
