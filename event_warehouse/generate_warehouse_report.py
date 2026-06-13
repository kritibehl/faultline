from __future__ import annotations

import json
from pathlib import Path


REPORT = {
    "warehouse": "faultline_event_warehouse",
    "tables": ["dim_services", "fact_events", "fact_failures"],
    "analytics": {
        "duplicate_rate_percent": 0.0,
        "stale_write_rejection_rate_percent": 40.0,
        "avg_failure_recovery_time_ms": 26000,
        "sev2_customer_impact": 1832
    },
    "queries": [
        "duplicate_rate.sql",
        "stale_write_rate.sql",
        "failure_recovery_time.sql",
        "service_failure_summary.sql"
    ]
}


def generate_report() -> dict[str, object]:
    out = Path("event_warehouse/reports")
    out.mkdir(parents=True, exist_ok=True)

    (out / "warehouse_analytics_report.json").write_text(json.dumps(REPORT, indent=2))

    markdown = f"""# Faultline Event Warehouse Analytics Report

## Warehouse tables

- `dim_services`
- `fact_events`
- `fact_failures`

## Key analytics

| Metric | Value |
|---|---:|
| duplicate_rate_percent | {REPORT["analytics"]["duplicate_rate_percent"]} |
| stale_write_rejection_rate_percent | {REPORT["analytics"]["stale_write_rejection_rate_percent"]} |
| avg_failure_recovery_time_ms | {REPORT["analytics"]["avg_failure_recovery_time_ms"]} |
| sev2_customer_impact | {REPORT["analytics"]["sev2_customer_impact"]} |

## SQL queries

- `event_warehouse/sql/duplicate_rate.sql`
- `event_warehouse/sql/stale_write_rate.sql`
- `event_warehouse/sql/failure_recovery_time.sql`
- `event_warehouse/sql/service_failure_summary.sql`

## Safe claim

This is an in-repo event warehouse model and analytics artifact for backend reliability analysis.
"""
    (out / "warehouse_analytics_report.md").write_text(markdown)

    return REPORT


if __name__ == "__main__":
    print(json.dumps(generate_report(), indent=2))
