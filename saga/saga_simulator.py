from __future__ import annotations

import json
from pathlib import Path


def run_saga_demo() -> dict[str, object]:
    scenario = json.loads(Path("saga/failure_scenarios.json").read_text())

    completed_steps = ["reserve_inventory", "charge_payment"]
    failed_step = scenario["failure"]["failed_step"]

    compensation_map = {
        "charge_payment": "refund_payment",
        "reserve_inventory": "release_inventory",
    }

    compensations = [
        compensation_map[step]
        for step in reversed(completed_steps)
        if step in compensation_map
    ]

    return {
        "workflow": scenario["workflow"],
        "failed_step": failed_step.replace("create_", ""),
        "compensations_executed": compensations,
        "final_state": "consistent",
    }


if __name__ == "__main__":
    print(json.dumps(run_saga_demo(), indent=2))
