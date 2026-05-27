
Customer Impact Summary
Primary customer risk

Silent duplicate commits can create incorrect downstream state.

Faultline mitigation
stale commits rejected at database boundary
duplicate-risk surfaced in metrics
replay artifacts preserve incident context
operators can inspect lease state and trace history
Tradeoff

Faultline may delay processing during unsafe coordination states, but this is preferable to silently accepting stale writes.
