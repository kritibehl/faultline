from __future__ import annotations

import json
from pathlib import Path
from collections import Counter


def tokenize(text: str) -> set[str]:
    return set(text.lower().replace("-", " ").split())


def similarity(a: str, b: str) -> float:
    ta = tokenize(a)
    tb = tokenize(b)

    if not ta or not tb:
        return 0.0

    overlap = len(ta & tb)
    union = len(ta | tb)
    return round(overlap / union, 4)


def load_incidents() -> list[dict]:
    out = []

    for p in Path("replays").glob("*.json"):
        data = json.loads(p.read_text())
        out.append(data)

    return out


def find_similar(query: str) -> list[dict]:
    scored = []

    for incident in load_incidents():
        text = (
            incident.get("failure_case", "") + " " +
            incident.get("observed_result", "")
        )

        score = similarity(query, text)

        scored.append({
            "failure_case": incident.get("failure_case"),
            "score": score,
        })

    return sorted(scored, key=lambda x: x["score"], reverse=True)


def main() -> None:
    query = "late stale worker commit after lease takeover"

    result = find_similar(query)

    Path("reports/incidents").mkdir(parents=True, exist_ok=True)

    out = {
        "query": query,
        "matches": result,
    }

    Path("reports/incidents/similarity_report.json").write_text(
        json.dumps(out, indent=2)
    )

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
