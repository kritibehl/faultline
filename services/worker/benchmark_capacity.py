from __future__ import annotations

import argparse
import json
import math


def synthetic_throughput(workers: int, retry_multiplier: float, degraded: bool) -> dict:
    base = workers * 42.0
    retry_penalty = 1.0 / retry_multiplier
    degraded_penalty = 0.58 if degraded else 1.0
    throughput = base * retry_penalty * degraded_penalty
    recovery_seconds = max(0.2, math.log2(max(workers, 1) + 1) * (3.2 if degraded else 0.8))
    return {
        "workers": workers,
        "retry_multiplier": retry_multiplier,
        "degraded": degraded,
        "throughput_jobs_per_min": round(throughput, 2),
        "recovery_seconds": round(recovery_seconds, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", nargs="+", type=int, default=[2, 4, 8, 16])
    parser.add_argument("--retry-multipliers", nargs="+", type=float, default=[1.0, 1.5, 2.0])
    args = parser.parse_args()

    rows = []
    for workers in args.workers:
        for retry_multiplier in args.retry_multipliers:
            rows.append(synthetic_throughput(workers, retry_multiplier, degraded=False))
            rows.append(synthetic_throughput(workers, retry_multiplier, degraded=True))

    print(json.dumps({"results": rows}, indent=2))


if __name__ == "__main__":
    main()
