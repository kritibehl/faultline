import json
from collections import defaultdict
from pathlib import Path

path = Path("artifacts/benchmarks/metrics_summary.json")
data = json.loads(path.read_text())["results"]

by_batch = defaultdict(list)
by_polling = defaultdict(list)
by_mode = defaultdict(list)

for r in data:
    if r["scenario"] == "baseline":
        by_batch[r["batch_size"]].append(r)
        by_polling[r["polling_mode"]].append(r)
        by_mode[r["mode"]].append(r)

def avg(rows, key):
    return round(sum(r[key] for r in rows) / max(1, len(rows)), 2)

lines = []
lines.append("| Dimension | Value | Throughput | p95 latency | Claim p95 | DB round trips | Empty polls |")
lines.append("|---|---:|---:|---:|---:|---:|---:|")

for batch, rows in sorted(by_batch.items()):
    lines.append(f"| batch_size | {batch} | {avg(rows, 'throughput_jobs_per_sec')} | {avg(rows, 'p95_latency_ms')} | {avg(rows, 'claim_latency_p95_ms')} | {avg(rows, 'db_round_trips_total')} | {avg(rows, 'empty_poll_cycles_total')} |")

for polling, rows in sorted(by_polling.items()):
    lines.append(f"| polling_mode | {polling} | {avg(rows, 'throughput_jobs_per_sec')} | {avg(rows, 'p95_latency_ms')} | {avg(rows, 'claim_latency_p95_ms')} | {avg(rows, 'db_round_trips_total')} | {avg(rows, 'empty_poll_cycles_total')} |")

for mode, rows in sorted(by_mode.items()):
    lines.append(f"| execution_mode | {mode} | {avg(rows, 'throughput_jobs_per_sec')} | {avg(rows, 'p95_latency_ms')} | {avg(rows, 'claim_latency_p95_ms')} | {avg(rows, 'db_round_trips_total')} | {avg(rows, 'empty_poll_cycles_total')} |")

out = Path("artifacts/benchmarks/comparison_table.md")
out.write_text("\n".join(lines) + "\n")
print(out)
