# Failure Model

Faultline is designed for:

- worker crash after claim
- delayed worker commit after lease expiry
- lease takeover races
- retry storms
- partial failure windows around commit and state update

Faultline does not claim to solve:

- Byzantine workers
- multi-region consensus
- exactly-once delivery to arbitrary external systems
- coordinator unavailability without PostgreSQL recovery

## Tradeoff

Faultline spends coordination overhead to buy stronger correctness at the commit boundary.
