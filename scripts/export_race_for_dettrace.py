import json
import pathlib
import sys

if len(sys.argv) != 2:
    print("usage: python3 scripts/export_race_for_dettrace.py <artifact.json>")
    sys.exit(1)

artifact_path = pathlib.Path(sys.argv[1])
data = json.loads(artifact_path.read_text())

out = artifact_path.with_suffix(".dettrace.jsonl")

def emit(actor, text, sink):
    for idx, line in enumerate(text.splitlines(), start=1):
        low = line.lower()
        event = None
        if "claim" in low:
            event = "JOB_CLAIMED"
        elif "lease" in low and "expire" in low:
            event = "LEASE_EXPIRED"
        elif "fenc" in low:
            event = "FENCING_EVENT"
        elif "stale" in low or "reject" in low:
            event = "STALE_COMMIT_REJECTED"
        elif "commit" in low:
            event = "COMMIT_ATTEMPT"
        elif "succeed" in low or "completed" in low:
            event = "JOB_SUCCEEDED"

        if event:
            sink.write(json.dumps({
                "actor": actor,
                "index": idx,
                "event": event,
                "line": line,
                "job_id": data["job_id"],
            }) + "\n")

with out.open("w") as sink:
    emit("worker-a", data.get("worker_a_log", ""), sink)
    emit("worker-b", data.get("worker_b_log", ""), sink)

print(out)
