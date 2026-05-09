from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    timeline = Path("docs/timeline/stale_worker_timeline.md").read_text()

    html = f"""
    <html>
    <head>
        <title>Faultline Incident Report</title>
    </head>
    <body>
        <h1>Faultline Incident Reconstruction</h1>

        <h2>Failure Class</h2>
        <p>stale_worker_race</p>

        <h2>Timeline</h2>
        <pre>{timeline}</pre>

        <h2>Outcome</h2>
        <p>stale worker commit rejected successfully</p>
    </body>
    </html>
    """

    Path("reports/incidents/failure_report.html").write_text(html)

    print("wrote reports/incidents/failure_report.html")


if __name__ == "__main__":
    main()
