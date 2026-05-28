# Home Automation Protocol Reliability Sequence

```text
Controller
   |
   | command(epoch=7, command_id=abc)
   v
Accessory
   |
   | ack(command_id=abc, applied_epoch=7)
   v
Controller state updated

Failure path:

Controller retry
   |
   | duplicate command_id=abc
   v
Accessory detects duplicate
   |
   | reject_duplicate
   v
Controller records idempotent success

Reconnect path:

Accessory offline
   |
   | reconnect
   v
Controller requests latest state
   |
   | stale command epoch detected
   v
Reject stale command
   |
   | retry with current epoch
   v
Safe state convergence
What this demonstrates
duplicate command prevention
stale command rejection
accessory reconnect recovery
state reconciliation
multi-hub failover reasoning
protocol-style correctness under failure
Safe scope

This is a HomeKit-style reliability simulation and protocol reasoning artifact. It does not claim Apple HomeKit implementation or real accessory certification.
