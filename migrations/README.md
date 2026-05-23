# Faultline Migration Artifacts

This directory contains Flyway-style migration examples for Faultline's PostgreSQL-backed correctness model.

## Files

- `V1__faultline_core_schema.sql`
- `V2__faultline_indexes.sql`
- `V3__faultline_retry_columns.sql`

## What they demonstrate

- job lifecycle schema
- fencing-token ownership column
- commit-log uniqueness
- lease-expiry indexes
- retry/dead-letter schema evolution

## Safe claim

These are migration artifacts and schema examples. They do not claim managed production migration infrastructure.
