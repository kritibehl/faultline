import json
import sys

if len(sys.argv) != 2:
    print("usage: python operator_explainer.py artifact.json")
    exit(1)

data = json.load(open(sys.argv[1]))

timeline = data.get("timeline", [])
events = [e["event"] for e in timeline]

def explain():
    result = {
        "what_failed": None,
        "why": None,
        "retry_safe": True,
        "next_steps": [],
        "owner": None,
    }

    if "fault_injected" in events:
        result["what_failed"] = "workflow interrupted by fault"
        result["why"] = "simulated timeout during processing"
        result["next_steps"] = [
            "check downstream dependency latency",
            "inspect retry logic",
        ]
        result["owner"] = "platform"

    if "retry_triggered" not in events:
        result["retry_safe"] = False

    return result

print(json.dumps(explain(), indent=2))
