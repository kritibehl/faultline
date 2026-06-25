
Partition Recovery Timeline
Time	Event	Expected behavior
T+00s	worker-a claims job	token=1 issued
T+03s	network partition begins	worker-a loses DB access
T+08s	heartbeat missing	lease-risk detected
T+18s	lease expires	job eligible for reclaim
T+19s	worker-b takes over	token advances to 2
T+22s	worker-b commits	accepted
T+24s	partition heals	worker-a resumes
T+25s	worker-a tries stale commit	rejected
T+26s	metrics updated	duplicate commits remain 0
Recovery metrics
{
  "duplicate_commits": 0,
  "stale_writes_rejected": 1,
  "partition_recovery_time_ms": 18000,
  "final_state": "consistent"
}

