# Home Automation Reliability Report

## Purpose

This scenario pack maps Faultline's distributed correctness model to HomeKit-style controller/accessory reliability scenarios.

## Validated scenarios

| Scenario | Reliability behavior |
|---|---|
| accessory_offline_reconnect | accessory reconnect state recovered |
| stale_controller_command | stale controller command rejected |
| duplicate_scene_command | duplicate scene prevented |
| multi_device_scene_replay | multi-device scene replay validated |
| controller_accessory_partition | controller/accessory partition handled |

## Reliability principles

- commands carry identity and epoch/version metadata
- accessory acknowledgements make state transitions reviewable
- duplicate scene commands are idempotent
- stale controller writes are rejected after state advances
- reconnect paths require state reconciliation

## Safe claim

This is a HomeKit-style distributed accessory simulation. It does not implement HomeKit, Matter, Thread, Bluetooth, or Apple protocols.
