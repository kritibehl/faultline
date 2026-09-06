import json
from pathlib import Path


ROOT = Path("artifacts/canonical")

UNSAFE = (
    ROOT
    / "bullmq-kill-post-commit-unsafe"
)

IDEMPOTENT = (
    ROOT
    / "bullmq-kill-post-commit-idempotent"
)


def load_report(path):
    return json.loads(
        (path / "report.json").read_text()
    )


def load_history(path):
    return [
        json.loads(line)
        for line in (
            path / "history.jsonl"
        ).read_text().splitlines()
        if line.strip()
    ]


def assert_crash_history(history):
    worker_a = [
        event["type"]
        for event in history
        if event["worker"] == "worker-a"
    ]

    assert "delivery_started" in worker_a
    assert "commit_accepted" in worker_a
    assert "ready_after_commit" in worker_a
    assert "fault_injected" in worker_a

    assert (
        "post_commit_window_exit"
        not in worker_a
    )

    assert any(
        event["type"]
        == "stalled_recovery_observed"
        for event in history
    )

    assert any(
        event["worker"] == "worker-b"
        and event["type"]
        == "delivery_started"
        and event["fencing_token"] == 2
        for event in history
    )


def test_bullmq_unsafe_crash_duplicates_effect():
    report = load_report(UNSAFE)
    history = load_history(UNSAFE)

    assert report["framework"] == "faultline"
    assert report["adapter"] == "bullmq"
    assert report["mode"] == "unsafe"
    assert report["fault"] == "kill"
    assert report["window"] == "post-commit"

    assert report["committed_effects"] == 2
    assert report["duplicate_suppressions"] == []
    assert report["current_fencing_token"] == 2
    assert report["result"] == "FAIL"

    assert {
        effect["fencing_token"]
        for effect in report["effects"]
    } == {1, 2}

    assert_crash_history(history)


def test_bullmq_idempotent_crash_suppresses_duplicate():
    report = load_report(IDEMPOTENT)
    history = load_history(IDEMPOTENT)

    assert report["framework"] == "faultline"
    assert report["adapter"] == "bullmq"
    assert report["mode"] == "idempotent"
    assert report["fault"] == "kill"
    assert report["window"] == "post-commit"

    assert report["committed_effects"] == 1

    assert len(
        report["duplicate_suppressions"]
    ) == 1

    assert (
        report["duplicate_suppressions"][0]
        ["fencing_token"]
        == 2
    )

    assert report["current_fencing_token"] == 2
    assert report["result"] == "PASS"

    assert_crash_history(history)
