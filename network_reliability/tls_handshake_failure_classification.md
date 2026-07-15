# TLS-like Handshake Failure Classification

## Purpose

Classify connection establishment failures during dependency communication.

## Failure categories

- handshake timeout
- certificate/authentication failure
- protocol mismatch
- connection reset

## Recovery workflow

- retry if transient
- fail closed if identity cannot be verified
- preserve replay artifacts
- avoid duplicate processing

## Safe claim

Classification artifact only; not a custom TLS implementation.
