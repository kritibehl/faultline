import json
from pathlib import Path


RUNS = Path("artifacts/runs")


def latest(pattern: str) -> Path:
    matches = sorted(RUNS.glob(pattern))

    if not matches:
        raise AssertionError(f"No artifact directories matching {pattern}")

    return matches[-1]


def load_report(path: Path) -> dict:
    return json.loads((path / "report.json").read_text())


def test_real_unsafe_celery_artifact_demonstrates_violation():
    run = latest("20*celery-unsafe-*")
    report = load_report(run)

    assert report["framework"] == "faultline"
    assert report["adapter"] == "celery"
    assert report["mode"] == "unsafe"
    assert report["invariant"] == "at-most-one-effect"
    assert report["committed_effects"] == 2
    assert report["current_fencing_token"] == 2
    assert report["result"] == "FAIL"


def test_real_fenced_celery_artifact_demonstrates_rejection():
    run = latest("20*celery-fenced-*")
    report = load_report(run)

    assert report["framework"] == "faultline"
    assert report["adapter"] == "celery"
    assert report["mode"] == "fenced"
    assert report["committed_effects"] == 1
    assert report["current_fencing_token"] == 2
    assert report["result"] == "PASS"

    assert len(report["stale_rejections"]) == 1

    rejection = report["stale_rejections"][0]

    assert rejection["worker"] == "worker-a"
    assert rejection["presented_token"] == 1
    assert rejection["current_token"] == 2
