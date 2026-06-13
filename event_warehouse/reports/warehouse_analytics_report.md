# Faultline Event Warehouse Analytics Report

## Warehouse tables

- `dim_services`
- `fact_events`
- `fact_failures`

## Key analytics

| Metric | Value |
|---|---:|
| duplicate_rate_percent | 0.0 |
| stale_write_rejection_rate_percent | 40.0 |
| avg_failure_recovery_time_ms | 26000 |
| sev2_customer_impact | 1832 |

## SQL queries

- `event_warehouse/sql/duplicate_rate.sql`
- `event_warehouse/sql/stale_write_rate.sql`
- `event_warehouse/sql/failure_recovery_time.sql`
- `event_warehouse/sql/service_failure_summary.sql`

## Safe claim

This is an in-repo event warehouse model and analytics artifact for backend reliability analysis.
