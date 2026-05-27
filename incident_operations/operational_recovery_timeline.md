
Operational Recovery Timeline
Example recovery sequence
Phase	Action	Signal
Detect	alert on duplicate-risk / expired leases	/metrics
Triage	inspect /health and trace export	inspector API
Reconstruct	replay claim/lease/commit events	replay browser
Mitigate	reduce workers or increase backoff	retry metrics stabilize
Recover	queue depth decreases	queue metrics
Review	complete incident template	incident review
Recovery quality signals
duplicate commit rate remains 0.0%
stale writes are rejected
queue backlog decreases
retry amplification stabilizes
safe_to_operate returns true
customer-impact summary completed
Engineering takeaway

Operational recovery is not just restoring throughput. For Faultline, recovery also requires proving that no unsafe stale commits were accepted.
