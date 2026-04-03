import json
import time
import uuid

def simulate_workflow():
    job_id = str(uuid.uuid4())

    timeline = []

    def event(name, meta=None):
        timeline.append({
            "ts": round(time.time(), 3),
            "event": name,
            "meta": meta or {}
        })

    event("request_received")
    event("job_queued")

    event("claim_acquired", {"worker": "worker-a", "token": 1})
    event("processing_started")

    # simulate fault
    time.sleep(1)
    event("fault_injected", {"type": "timeout"})

    # retry / failure handling
    event("retry_triggered")

    event("claim_acquired", {"worker": "worker-b", "token": 2})
    event("processing_resumed")

    event("completed")

    path = f"artifacts/races/demo-{job_id}.json"
    with open(path, "w") as f:
        json.dump({
            "job_id": job_id,
            "timeline": timeline
        }, f, indent=2)

    print(path)

if __name__ == "__main__":
    simulate_workflow()
