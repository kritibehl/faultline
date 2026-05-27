
Availability vs Consistency Review
Design choice

Faultline prioritizes commit correctness over accepting writes when the correctness boundary cannot validate ownership.

Consistency behavior

A worker can only commit when its submitted fencing token matches the current database fencing token.

Availability impact

If PostgreSQL is unavailable or commit validation cannot run, Faultline should retry or fail closed rather than accepting an unvalidated result.

Customer framing

For correctness-sensitive workloads, a delayed result is usually preferable to a duplicated or stale commit.
