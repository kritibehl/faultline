# Faultline Failure Timeline

| Step | Phase | Job | Worker | Fencing Token | Timestamp |
|---:|---|---|---|---:|---|
| 1 | claim_job | job-1 | worker-a | 1 | 2026-05-09T03:05:37.862797+00:00 |
| 2 | acquire_lease | job-1 | worker-a | 1 | 2026-05-09T03:05:37.863175+00:00 |
| 3 | lease_takeover | job-1 | worker-b | 2 | 2026-05-09T03:05:37.863178+00:00 |
| 4 | commit_result | job-1 | worker-b | 2 | 2026-05-09T03:05:37.863180+00:00 |
| 5 | reject_stale_write | job-1 | worker-a | 1 | 2026-05-09T03:05:37.863181+00:00 |

## Interpretation

This timeline reconstructs ownership transitions and shows where stale-worker commits are rejected.
