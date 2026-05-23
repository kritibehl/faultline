# NATS Faultline Bridge

Faultline can model NATS as an event-ingress layer while keeping PostgreSQL as the correctness boundary.

## Flow

NATS event -> Faultline enqueue -> worker claim -> fencing-token commit -> trace/metrics export

## Why NATS

- lightweight pub/sub
- simple operational model
- useful for event-driven job ingestion

## Safe claim

This repo documents NATS integration design. PostgreSQL remains the source of commit correctness.
