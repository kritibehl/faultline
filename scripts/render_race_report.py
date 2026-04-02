import json
import sys
from pathlib import Path

from services.reporting.race_reports import build_race_report, explain_report

if len(sys.argv) != 2:
    print("usage: python3 scripts/render_race_report.py <artifact.json>")
    sys.exit(1)

path = Path(sys.argv[1])
artifact = json.loads(path.read_text())
report = build_race_report(artifact)
report["root_cause"] = explain_report(report)

out = path.with_suffix(".report.json")
out.write_text(json.dumps(report, indent=2))
print(out)
