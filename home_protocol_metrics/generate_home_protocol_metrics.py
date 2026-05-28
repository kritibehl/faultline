from __future__ import annotations

import json
from pathlib import Path


METRICS = {
    "pairing_success_rate": 1.0,
    "avg_ack_latency_ms": 32,
    "p95_ack_latency_ms": 58,
    "avg_recovery_time_ms": 420,
    "p95_recovery_time_ms": 690,
    "duplicate_commands_prevented": 12,
    "stale_commands_rejected": 7,
    "failover_duration_ms": 850,
    "devices_online": 8,
    "devices_offline": 1,
    "pairing_events": 5,
    "failovers": 2,
    "reconnects": 4,
    "network_degradation_events": {
        "packet_loss": 3,
        "delayed_ack": 4,
        "duplicate_ack": 2,
        "reordered_command": 2
    },
    "safe_claim": "synthetic HomeKit-style protocol reliability metrics, not Apple HomeKit telemetry"
}


def main() -> None:
    out = Path("home_protocol_metrics")
    out.mkdir(parents=True, exist_ok=True)

    (out / "home_protocol_metrics.json").write_text(json.dumps(METRICS, indent=2))

    summary = f"""# Home Protocol Metrics Summary

## Key measurements

| Metric | Value |
|---|---:|
| pairing_success_rate | {METRICS["pairing_success_rate"]} |
| avg_ack_latency_ms | {METRICS["avg_ack_latency_ms"]} |
| p95_ack_latency_ms | {METRICS["p95_ack_latency_ms"]} |
| avg_recovery_time_ms | {METRICS["avg_recovery_time_ms"]} |
| p95_recovery_time_ms | {METRICS["p95_recovery_time_ms"]} |
| duplicate_commands_prevented | {METRICS["duplicate_commands_prevented"]} |
| stale_commands_rejected | {METRICS["stale_commands_rejected"]} |
| failover_duration_ms | {METRICS["failover_duration_ms"]} |
| devices_online | {METRICS["devices_online"]} |
| devices_offline | {METRICS["devices_offline"]} |
| pairing_events | {METRICS["pairing_events"]} |
| failovers | {METRICS["failovers"]} |
| reconnects | {METRICS["reconnects"]} |

## Interpretation

The protocol lab tracks pairing success, acknowledgement latency, recovery time, duplicate-command prevention, stale-command rejection, failover duration, device availability, and reconnect behavior.

## Safe claim

These are synthetic HomeKit-style reliability metrics for protocol simulation review. They are not Apple HomeKit telemetry.
"""
    (out / "home_protocol_metrics_summary.md").write_text(summary)

    print(json.dumps(METRICS, indent=2))


if __name__ == "__main__":
    main()
