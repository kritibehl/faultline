import json
from pathlib import Path


CANONICAL = Path("artifacts/canonical")

UNSAFE = CANONICAL / "celery-pause-unsafe"
FENCED = CANONICAL / "celery-pause-fenced"


def load_report(path: Path) -> dict:
    return json.loads((path / "report.json").read_text())


def test_canonical_unsafe_run_demonstrates_duplicate_effect():
    report = load_report(UNSAFE)

    assert report["framework"] == "faultline"
    assert report["adapter"] == "celery"
    assert report["mode"] == "unsafe"

    assert report["fault"] == "pause"
    assert report["fault_injection"] == {
        "inject": "SIGSTOP",
        "recover": "SIGCONT",
    }

    assert report["invariant"] == "at-most-one-effect"
    assert report["invariant_observed"] == 2
    assert report["invariant_limit"] == 1

    assert report["committed_effects"] == 2
    assert report["current_fencing_token"] == 2
    assert report["stale_rejections"] == []
    assert report["result"] == "FAIL"

    tokens = {
        effect["fencing_token"]
        for effect in report["effects"]
    }

    assert tokens == {1, 2}


def test_canonical_fenced_run_rejects_stale_owner():
    report = load_report(FENCED)

    assert report["framework"] == "faultline"
    assert report["adapter"] == "celery"
    assert report["mode"] == "fenced"

    assert report["fault"] == "pause"
    assert report["fault_injection"] == {
        "inject": "SIGSTOP",
        "recover": "SIGCONT",
    }

    assert report["invariant"] == "at-most-one-effect"
    assert report["invariant_observed"] == 1
    assert report["invariant_limit"] == 1

    assert report["committed_effects"] == 1
    assert report["current_fencing_token"] == 2
    assert report["result"] == "PASS"

    assert len(report["effects"]) == 1
    assert report["effects"][0]["worker"] == "worker-b"
    assert report["effects"][0]["fencing_token"] == 2

    assert len(report["stale_rejections"]) == 1

    rejection = report["stale_rejections"][0]

    assert rejection["worker"] == "worker-a"
    assert rejection["presented_token"] == 1
    assert rejection["current_token"] == 2
