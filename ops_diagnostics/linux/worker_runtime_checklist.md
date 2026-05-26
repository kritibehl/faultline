
Worker Runtime Debugging Checklist
When workers appear stuck

Check:

process still alive
database connectivity
active PostgreSQL connections
expired leases
retry count growth
stale-write rejection count
queue delay
Commands
curl http://localhost:8088/health
curl http://localhost:8088/metrics
docker logs faultline-postgres --tail 50
Decision guide
Symptom	Likely cause	Action
expired leases rising	workers slow or paused	inspect CPU/memory and lease duration
retry count rising	dependency failure	inspect downstream system
commit latency rising	DB contention	inspect locks and indexes
duplicate risk rising	stale workers present	verify fencing-token rejection
