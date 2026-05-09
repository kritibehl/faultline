import json
from pathlib import Path

required = {"failure_case", "expected_behavior", "observed_result", "metric"}

failed = 0

for p in Path("replays").glob("*.json"):
    data = json.loads(p.read_text())
    missing = required - set(data)
    if missing:
        print(f"FAIL {p}: missing {sorted(missing)}")
        failed += 1
    else:
        print(f"OK {p}: {data['failure_case']}")

raise SystemExit(1 if failed else 0)
