import json
from pathlib import Path

from home_protocol_metrics.generate_home_protocol_metrics import METRICS


def test_home_protocol_metrics_have_expected_reliability_signals():
    assert METRICS["pairing_success_rate"] == 1.0
    assert METRICS["avg_ack_latency_ms"] == 32
    assert METRICS["duplicate_commands_prevented"] == 12
    assert METRICS["stale_commands_rejected"] == 7
    assert METRICS["failover_duration_ms"] == 850


def test_home_protocol_metrics_file_generated():
    path = Path("home_protocol_metrics/home_protocol_metrics.json")
    assert path.exists()

    data = json.loads(path.read_text())
    assert data["pairing_success_rate"] == 1.0
    assert data["devices_online"] == 8
    assert data["devices_offline"] == 1


def test_home_automation_dashboard_exists():
    path = Path("home_automation_dashboard/home_automation_dashboard.html")
    assert path.exists()

    html = path.read_text()
    assert "Devices Online" in html
    assert "Stale Commands Rejected" in html
    assert "Hub Failover" in html
