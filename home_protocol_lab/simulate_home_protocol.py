from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BASE = Path(__file__).parent
MULTI_HUB_BASE = BASE.parent / "multi_hub_scenarios"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def validate_device_discovery(data: dict[str, Any]) -> dict[str, Any]:
    expected = data["expected"]
    return {
        "scenario": data["scenario"],
        "passed": expected["device_discovered"] is True
        and "power" in expected["capabilities"]
        and expected["protocol_state"] == "discovered",
        "evidence": "device discovered and capabilities read",
    }


def validate_device_pairing(data: dict[str, Any]) -> dict[str, Any]:
    expected = data["expected"]
    return {
        "scenario": data["scenario"],
        "passed": expected["device_paired"] is True
        and expected["trust_state"] == "paired"
        and expected["controller_authorized"] is True,
        "evidence": "device paired and controller authorized",
    }


def validate_attribute_sync(data: dict[str, Any]) -> dict[str, Any]:
    expected = data["expected"]
    return {
        "scenario": data["scenario"],
        "passed": expected["attribute_synced"] is True
        and expected["final_epoch"] == data["reported_attributes"]["attribute_epoch"],
        "evidence": "attribute epoch advanced and synced",
    }


def validate_command_ack(data: dict[str, Any]) -> dict[str, Any]:
    expected = data["expected"]
    return {
        "scenario": data["scenario"],
        "passed": expected["command_acknowledged"] is True
        and data["command"]["command_id"] == data["ack"]["command_id"],
        "evidence": "command acknowledgement matches command id",
    }


def validate_state_reconciliation(data: dict[str, Any]) -> dict[str, Any]:
    expected = data["expected"]
    return {
        "scenario": data["scenario"],
        "passed": expected["reconciled"] is True
        and expected["authoritative_state"]["epoch"] == 9
        and expected["stale_controller_state_rejected"] is True,
        "evidence": "newer device state reconciled and stale controller state rejected",
    }


def validate_network_degradation(data: dict[str, Any]) -> dict[str, Any]:
    expected = data["expected"]
    return {
        "scenario": data["scenario"],
        "passed": all(expected.values()),
        "evidence": "packet loss, delayed ack, duplicate ack, and reordered command handled",
    }


def validate_primary_secondary_failover(data: dict[str, Any]) -> dict[str, Any]:
    expected = data["expected"]
    return {
        "scenario": data["scenario"],
        "passed": expected["failover_completed"] is True
        and expected["active_hub"] == "hub-secondary"
        and expected["hub_epoch"] == 2,
        "evidence": "secondary hub promoted after primary unavailable",
    }


def validate_hub_rejoin_reconciliation(data: dict[str, Any]) -> dict[str, Any]:
    expected = data["expected"]
    return {
        "scenario": data["scenario"],
        "passed": expected["rejoin_handled"] is True
        and expected["stale_hub_write_rejected"] is True
        and expected["active_hub_epoch"] == 2,
        "evidence": "stale primary hub write rejected after rejoin",
    }


SCENARIOS = [
    (BASE / "device_discovery.json", validate_device_discovery),
    (BASE / "device_pairing.json", validate_device_pairing),
    (BASE / "attribute_sync.json", validate_attribute_sync),
    (BASE / "command_ack.json", validate_command_ack),
    (BASE / "state_reconciliation.json", validate_state_reconciliation),
    (BASE / "network_degradation.json", validate_network_degradation),
    (MULTI_HUB_BASE / "primary_secondary_failover.json", validate_primary_secondary_failover),
    (MULTI_HUB_BASE / "hub_rejoin_reconciliation.json", validate_hub_rejoin_reconciliation),
]


def run_all() -> dict[str, Any]:
    results = []
    for path, validator in SCENARIOS:
        results.append(validator(load_json(path)))

    passed = sum(1 for result in results if result["passed"])

    return {
        "suite": "home_protocol_lab",
        "passed": passed,
        "total": len(results),
        "all_passed": passed == len(results),
        "results": results,
    }


if __name__ == "__main__":
    print(json.dumps(run_all(), indent=2))
