from dataclasses import dataclass
from typing import Any

@dataclass
class WorkflowStep:
    name: str
    kind: str  # plan, tool_call, validation, commit, fallback

def run_workflow(job_id: str, steps: list[WorkflowStep]) -> dict[str, Any]:
    # Persist plan -> tool_call -> validation -> commit
    # Each step should be idempotent and stateful.
    return {"job_id": job_id, "steps": [s.name for s in steps]}
