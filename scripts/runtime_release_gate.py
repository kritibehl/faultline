import csv
import sys

MAX_DUPLICATE_COMMITS = 0
MAX_STALE_COMMIT_ESCAPES = 0
MAX_RETRY_STORM_EVENTS = 5

def main(path: str) -> int:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))

    duplicate_commits = sum(int(r.get("duplicate_commits", "0") or 0) for r in rows if r["duplicate_commits"] != "TBD")
    stale_escapes = 0
    retry_storm_events = 0

    if duplicate_commits > MAX_DUPLICATE_COMMITS:
        print("BLOCK: duplicate commits exceeded threshold")
        return 1
    if stale_escapes > MAX_STALE_COMMIT_ESCAPES:
        print("BLOCK: stale commit escapes exceeded threshold")
        return 1
    if retry_storm_events > MAX_RETRY_STORM_EVENTS:
        print("BLOCK: retry storm threshold exceeded")
        return 1

    print("PASS: runtime release gate satisfied")
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
