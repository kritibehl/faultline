from pathlib import Path

from event_warehouse.generate_warehouse_report import generate_report


def test_event_warehouse_report_contains_required_tables_and_metrics():
    report = generate_report()

    assert "fact_events" in report["tables"]
    assert "fact_failures" in report["tables"]
    assert "dim_services" in report["tables"]

    assert report["analytics"]["duplicate_rate_percent"] == 0.0
    assert report["analytics"]["stale_write_rejection_rate_percent"] == 40.0
    assert report["analytics"]["avg_failure_recovery_time_ms"] == 26000


def test_event_warehouse_sql_queries_exist():
    required = [
        "event_warehouse/sql/duplicate_rate.sql",
        "event_warehouse/sql/stale_write_rate.sql",
        "event_warehouse/sql/failure_recovery_time.sql",
        "event_warehouse/sql/service_failure_summary.sql",
    ]

    for path in required:
        assert Path(path).exists()


def test_event_warehouse_reports_written():
    generate_report()

    assert Path("event_warehouse/reports/warehouse_analytics_report.json").exists()
    assert Path("event_warehouse/reports/warehouse_analytics_report.md").exists()
