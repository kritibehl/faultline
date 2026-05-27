
Operational Cost Notes
Cost drivers
polling frequency
worker concurrency
batch size
lease duration
retry volume
trace and replay retention
database connection pool size
Cost vs resilience tradeoffs
Lever	Benefit	Cost
shorter poll interval	faster recovery	higher database load
larger batch size	fewer claim round trips	fairness risk
longer lease duration	fewer false takeovers	slower crash recovery
richer tracing	better debugging	more storage
Summary

Faultline intentionally spends coordination cost to protect correctness under failure.
