import json
import sys

if len(sys.argv) != 2:
    print("usage: python render_workflow_timeline.py file.json")
    exit(1)

data = json.load(open(sys.argv[1]))

print("\n=== WORKFLOW TIMELINE ===\n")

for i, ev in enumerate(data["timeline"], 1):
    print(f"{i}. {ev['event']} -> {ev.get('meta', {})}")

print("\n========================\n")
