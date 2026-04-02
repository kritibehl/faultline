import json
import pathlib
import sys

if len(sys.argv) != 2:
    print("usage: python3 scripts/explain_race.py <artifact.json>")
    sys.exit(1)

artifact_path = pathlib.Path(sys.argv[1])
data = json.loads(artifact_path.read_text())

wa = data.get("worker_a_log", "").lower()
wb = data.get("worker_b_log", "").lower()
fs = data.get("final_state", {})

points = []

if fs.get("state") == "succeeded":
    points.append("Job reached terminal success.")
else:
    points.append("Job did not reach terminal success.")

if fs.get("fencing_token", 0) >= 2:
    points.append("Reclaim likely occurred because fencing token advanced beyond the first claim.")
else:
    points.append("Reclaim was not clearly proven because fencing token did not advance beyond 1.")

if any(k in wa for k in ["stale", "fence", "reject"]):
    points.append("Worker A shows evidence of stale or fenced commit rejection.")
else:
    points.append("Worker A log does not yet clearly prove stale-commit rejection.")

if any(k in wb for k in ["claim", "succeed", "commit"]):
    points.append("Worker B log shows evidence of reclaim and completion path.")
else:
    points.append("Worker B log does not yet clearly prove reclaim/completion path.")

report = artifact_path.with_suffix(".explanation.md")
with report.open("w") as f:
    f.write("# Faultline Root-Cause Explanation\n\n")
    for p in points:
        f.write(f"- {p}\n")

print(report)
