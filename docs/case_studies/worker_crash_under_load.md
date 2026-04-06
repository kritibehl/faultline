# Worker Crash Under Load

## What was injected
A worker crash before completion write under concurrent execution load.

## What happened
The in-flight job became reclaimable after lease expiry and was recovered by another worker path.

## What guarantee held
No duplicate commit was accepted; correctness was preserved through reclaim semantics and stale-write protection.

## What degraded
Throughput dropped during recovery and tail latency rose during the reclaim window.

## What changed after tuning
Batch claiming and adaptive polling reduced coordination overhead, while safer lease tuning improved recovery stability for longer-running workloads.
