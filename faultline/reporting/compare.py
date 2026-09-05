from __future__ import annotations

import json
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def print_comparison(
    unsafe_report: Path,
    fenced_report: Path,
) -> None:
    unsafe = load(unsafe_report)
    fenced = load(fenced_report)

    print()
    print("Faultline Correctness Comparison")
    print("================================")
    print()
    print(f"{'':24} {'UNSAFE':>10} {'FENCED':>10}")
    print("-" * 46)

    print(
        f"{'Committed effects':24}"
        f"{unsafe['committed_effects']:>10}"
        f"{fenced['committed_effects']:>10}"
    )

    print(
        f"{'Stale rejections':24}"
        f"{len(unsafe['stale_rejections']):>10}"
        f"{len(fenced['stale_rejections']):>10}"
    )

    print(
        f"{'Current token':24}"
        f"{unsafe['current_fencing_token']:>10}"
        f"{fenced['current_fencing_token']:>10}"
    )

    print(
        f"{'Invariant':24}"
        f"{unsafe['result']:>10}"
        f"{fenced['result']:>10}"
    )

    print()
