from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

SCENARIOS = [
    "healthy",
    "packet_loss",
    "asymmetric_latency",
    "bursty_link_degradation",
    "dns_failure",
    "partial_partition",
    "intermittent_handshake",
]


def run_scenario(profile: str, seconds: int) -> dict:
    env = os.environ.copy()
    env["FAULTLINE_NETWORK_PROFILE"] = profile
    proc = subprocess.Popen(
        [sys.executable, "-m", "services.worker.worker"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    start = time.time()
    time.sleep(seconds)
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
    return {
        "profile": profile,
        "duration_seconds": round(time.time() - start, 2),
        "status": "completed",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=3)
    parser.add_argument("--profiles", nargs="*", default=SCENARIOS)
    args = parser.parse_args()

    results = [run_scenario(profile, args.seconds) for profile in args.profiles]
    print(json.dumps({"results": results}, indent=2))


if __name__ == "__main__":
    main()
