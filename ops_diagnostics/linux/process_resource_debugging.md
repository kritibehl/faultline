# Linux Process and Resource Debugging Notes

## Purpose

Faultline workers can fail or slow down due to CPU, memory, file descriptor, or network pressure. These notes document practical Linux debugging workflows.

## Process inspection

```bash
ps aux | grep faultline
top -o cpu
top -o mem
File descriptors
lsof -p <pid>
ulimit -n
Network and ports
lsof -i :8088
netstat -an | grep 5432
CPU / memory pressure
vm_stat
uptime

Linux equivalents:

free -m
vmstat 1
pidstat 1
Container diagnostics
docker ps
docker stats
docker logs faultline-postgres --tail 50
Faultline-specific checks
inspector /health
inspector /metrics
expired lease count
duplicate-risk count
retry growth
stale-write rejection count
Engineering interpretation

Runtime resource pressure can amplify lease expiry, retry growth, and queue delay. Faultline should surface those signals through metrics rather than silently accepting stale commits.
