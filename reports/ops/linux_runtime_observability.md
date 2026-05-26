# Linux Runtime Observability Experiments

## Purpose

Document process/resource debugging workflows for Faultline workers and inspector services.

## Experiments

### CPU saturation

Signal:
- worker latency rises
- lease expiry increases
- retry queue grows

Commands:
```bash
top
vmstat 1
pidstat 1
Memory pressure

Signal:

worker process restart
queue backlog growth
increased retry attempts

Commands:

top -o mem
docker stats
File descriptor exhaustion

Signal:

DB connection failures
inspector endpoint errors
failed connection pool stress attempts

Commands:

ulimit -n
lsof -p <pid>
Container restart diagnostics

Commands:

docker ps
docker logs faultline-postgres --tail 50
docker inspect faultline-postgres
Faultline-specific checks
curl http://localhost:8088/health
curl http://localhost:8088/metrics
Engineering takeaway

Runtime pressure should surface through expired leases, retry growth, queue depth, and stale-worker rejection counters instead of silently corrupting committed state.
