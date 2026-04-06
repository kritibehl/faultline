# Faultline Formal Spec

This folder contains a minimal TLA+ model for Faultline's fencing-token behavior.

## What this models

The model focuses on three ideas:

- ownership is time-bounded
- fencing tokens increase on each new claim
- a commit is valid only for the current owner with the current token

## What this validates

This spec is intended to validate:

- stale-writer exclusion
- single-winner reclaim behavior
- monotonic token progression across claim epochs

## Important scope note

This is a small safety model for the fencing-token protocol.
It does not model the entire Faultline system.
