
Faultline Connection Pool Report
Signals to watch
Signal	Risk
active connections	pool pressure
idle in transaction	lock retention
claim latency	coordinator contention
commit latency	commit-boundary contention
retry growth	downstream instability
Recommended actions
reduce worker concurrency when lock waits dominate
increase batch size when round trips dominate
increase lease duration when valid work exceeds lease window
add indexes before scaling workers
