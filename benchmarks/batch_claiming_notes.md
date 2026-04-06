# Batch Claiming Plan

Supported batch sizes:
- 1
- 5
- 10
- 25

Measured outcomes:
- throughput improvement
- claim latency
- tail latency
- DB round-trip reduction
- fairness shift
- starvation side effects

This layer models the coordination-cost reduction gained by amortizing claim overhead across more useful work per DB interaction.
