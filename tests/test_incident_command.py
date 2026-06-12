from pathlib import Path

from incident_command.generate_incident_command_report import release_incident_command_report


def test_incident_command_report_has_tesla_style_ownership_signals():
    report = release_incident_command_report()

    assert report["severity"] == "sev2"
    assert report["customer_impact"] == 1832
    assert report["mitigation"] == "traffic_reroute"
    assert report["recovery_time_min"] == 18
    assert report["correctness_status"]["duplicate_commits"] == 0
    assert report["correctness_status"]["stale_writes_accepted"] == 0


def test_incident_command_artifacts_exist():
    release_incident_command_report()

    required = [
        "incident_command/incident_bridge.md",
        "incident_command/executive_update.md",
        "incident_command/customer_impact_summary.md",
        "incident_command/postmortem.md",
        "incident_command/incident_command_report.json"
    ]

    for path in required:
        assert Path(path).exists()
