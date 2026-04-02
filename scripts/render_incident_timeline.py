import json
import pathlib
import re
import sys

if len(sys.argv) != 2:
    print("usage: python3 scripts/render_incident_timeline.py <artifact.json>")
    sys.exit(1)

artifact_path = pathlib.Path(sys.argv[1])
data = json.loads(artifact_path.read_text())

def extract_events(label, text):
    out = []
    for line in text.splitlines():
        low = line.lower()
        if any(k in low for k in ["claim", "lease", "fenc", "commit", "stale", "succeed", "reject", "reap"]):
            out.append({"actor": label, "line": line})
    return out

events = []
events.extend(extract_events("worker-a", data.get("worker_a_log", "")))
events.extend(extract_events("worker-b", data.get("worker_b_log", "")))

timeline = artifact_path.with_suffix(".timeline.md")
with timeline.open("w") as f:
    f.write(f"# Faultline Incident Timeline\n\n")
    f.write(f"Job ID: `{data['job_id']}`\n\n")
    f.write("## Final State\n\n")
    f.write("```json\n")
    f.write(json.dumps(data.get("final_state", {}), indent=2))
    f.write("\n```\n\n")
    f.write("## Evidence Timeline\n\n")
    if not events:
        f.write("_No recognizable claim/lease/fencing events found in logs._\n")
    else:
        for i, ev in enumerate(events, start=1):
            f.write(f"{i}. **{ev['actor']}** — `{ev['line']}`\n")

print(timeline)
