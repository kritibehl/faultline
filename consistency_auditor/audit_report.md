# Nightly Consistency Audit Report

## Purpose

Faultline includes a consistency auditor for comparing job state, event records, and outbox records.

## Checks

- orphan event records
- orphan outbox records
- duplicate outbox idempotency keys
- succeeded jobs missing completion events

## Tables reviewed

- job table
- event table
- outbox table

## Why this matters

Distributed worker systems can appear healthy while internal records drift. A nightly audit catches inconsistencies before they become customer-visible incidents.

## Safe claim

This is an in-repo consistency-audit simulation, not a production scheduled audit service.
