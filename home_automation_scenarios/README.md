# Home Automation Reliability Scenarios

Faultline includes HomeKit-style distributed accessory simulations for:

- offline accessory reconnect recovery
- stale controller command rejection
- duplicate scene prevention
- multi-device scene replay validation
- controller/accessory partition recovery

Run:

```bash
PYTHONPATH=. python3 home_automation_scenarios/run_home_automation_replay.py
Expected result:

5/5 scenarios passed

Safe claim: these are HomeKit-style reliability simulations, not Apple HomeKit protocol implementations.
