# Home Automation Protocol Reliability

## Purpose

This document maps Faultline's correctness-under-failure model to HomeKit-style controller/accessory coordination.

Safe claim: this is a protocol-style reliability design document. It does not implement HomeKit, Matter, Thread, Bluetooth, or Apple ecosystem protocols.

## Core entities

| Entity | Responsibility |
|---|---|
| Controller | issues commands and scene requests |
| Accessory | applies state transitions and emits acknowledgements |
| Command ID | supports deduplication and replay analysis |
| Accessory epoch | prevents stale controller writes |
| Acknowledgement | confirms applied state |
| Replay artifact | reconstructs distributed failure sequence |

## Device state

Each accessory has state plus an epoch/version:

```text
accessory_id
state
accessory_epoch
last_applied_command_id

The epoch advances when authoritative state changes.

Controller command

A controller command includes:

command_id
controller_id
accessory_id
controller_epoch
target_state
idempotency_key

The accessory rejects commands whose epoch is older than the current accessory epoch.

Accessory acknowledgement

An acknowledgement includes:

command_id
accessory_id
applied_state
accessory_epoch
status

This makes multi-device scene execution replayable.

Reconnect path

When an accessory reconnects:

controller requests reported state
accessory reports current state and epoch
controller compares expected state with reported state
system reconciles missing or stale commands
replay artifact records recovery
Stale command rejection

A stale command is rejected when:

submitted_controller_epoch < current_accessory_epoch

This mirrors Faultline's stale-worker rejection pattern:

submitted_fencing_token < current_fencing_token
Duplicate prevention

Duplicate scene commands are prevented using:

command_id
idempotency_key
last_applied_command_id
scene execution record
Multi-device scene replay

A scene is complete only when all required accessory acknowledgements are present.

Replay validates:

command order
acknowledgement count
missing accessory responses
stale command rejection
duplicate command prevention
Reliability takeaway

Home automation reliability requires the same distributed-systems discipline as backend worker execution: state versioning, stale-write rejection, deduplication, acknowledgement tracking, and replayable recovery.

## Home Protocol Lab Extension

Faultline also includes a home protocol lab covering:

- device discovery
- device pairing
- attribute synchronization
- command acknowledgements
- state reconciliation
- network degradation handling
- primary/secondary hub failover
- stale hub rejoin rejection

This extends the controller-accessory reliability model beyond command replay into protocol lifecycle behavior.
