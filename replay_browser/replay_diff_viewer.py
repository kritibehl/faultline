from __future__ import annotations

import json
from pathlib import Path


def load(name: str):
    return json.loads(Path(name).read_text())


def diff(a: dict, b: dict):
    out = {}

    keys = set(a.keys()) | set(b.keys())

    for k in sorted(keys):
        av = a.get(k)
        bv = b.get(k)

        if av != bv:
            out[k] = {
                "left": av,
                "right": bv,
            }

    return out


def main():
    files = sorted(Path("replays").glob("*.json"))

    if len(files) < 2:
        raise SystemExit("need at least 2 replay files")

    left = load(str(files[0]))
    right = load(str(files[1]))

    result = {
        "left": files[0].name,
        "right": files[1].name,
        "diff": diff(left, right),
    }

    Path("reports/replays").mkdir(parents=True, exist_ok=True)

    Path("reports/replays/replay_diff.json").write_text(
        json.dumps(result, indent=2)
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
