from __future__ import annotations

import json
from pathlib import Path


def load():
    out = []

    for p in Path("replays").glob("*.json"):
        data = json.loads(p.read_text())
        data["_file"] = p.name
        out.append(data)

    return out


def search(term: str):
    matches = []

    for replay in load():
        text = json.dumps(replay).lower()

        if term.lower() in text:
            matches.append({
                "file": replay["_file"],
                "failure_case": replay.get("failure_case"),
            })

    return matches


def main():
    query = "lease"

    result = {
        "query": query,
        "matches": search(query),
    }

    Path("reports/replays").mkdir(parents=True, exist_ok=True)

    Path("reports/replays/search_results.json").write_text(
        json.dumps(result, indent=2)
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
