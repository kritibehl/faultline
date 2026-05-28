# Home Protocol Lab

This lab extends Faultline's distributed correctness model into HomeKit-style controller/accessory reliability workflows.

## Scenarios

- device discovery
- device pairing
- attribute sync
- command acknowledgement
- state reconciliation
- packet loss / delayed ack / duplicate ack / reordered command
- primary/secondary hub failover
- stale hub rejoin rejection

Run:

```bash
PYTHONPATH=. python3 home_protocol_lab/simulate_home_protocol.py
Safe claim: this is a home-automation protocol reliability simulation, not a HomeKit/Matter/Thread implementation.
