
Cost and Resilience Tradeoffs
Operational cost drivers
worker concurrency
polling interval
lease duration
retry amplification
trace/report retention
database connection pool size
Resilience levers
Lever	Improves	Tradeoff
longer lease duration	fewer premature reclaims	slower crash recovery
shorter poll interval	faster recovery	more database load
larger batch size	lower claim overhead	fairness/starvation risk
retry backoff	reduces retry storms	increases delay
Summary

Faultline intentionally spends coordination cost to preserve correctness under failure.
