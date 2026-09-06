import json
from pathlib import Path


CANONICAL = Path("artifacts/canonical")

UNSAFE = CANONICAL / "celery-kill-post-commit-unsafe"
FENCED = CANONICAL / "celery-kill-post-commit-fenced"
IDEMPOTENT = CANONICAL / "celery-kill-post-commit-idempotent"


def load_report(path: Path) -> dict:
    return json.loads(
        (path / "report.json").read_text()
    )


def load_history(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (path / "history.jsonl")
        .read_text()
        .splitlines()
        if line.strip()
    ]


def assert_kill_report(
    report: dict,
    *,
    mode: str,
    effects: int,
    result: str,
) -> None:
    assert report["framework"] == "faultline"
    assert report["adapter"] == "celery"
    assert report["mode"] == mode
    assert report["window"] == "post-commit"

    assert report["fault"] == "kill"
    assert report["fault_injection"] == {
        "inject": "SIGKILL",
        "recover": "docker start",
    }

    assert report["invariant"] == "at-most-one-effect"
    assert report["committed_effects"] == effects
    assert report["invariant_observed"] == effects
    assert report["invariant_limit"] == 1
    assert report["current_fencing_token"] == 2
    assert report["stale_rejections"] == []
    assert report["result"] == result


def assert_original_execution_never_resumed(
    history: list[dict],
) -> None:
    worker_a_events = [
        event["type"]
        for event in history
        if event["worker"] == "worker-a"
    ]

    assert "commit_accepted" in worker_a_events
    assert "ready_after_commit" in worker_a_events
    assert "fault_injected" in worker_a_events
    assert "fault_recovered" in worker_a_events

    assert "post_commit_window_exit" not in worker_a_events


def test_kill_post_commit_unsafe_duplicates_effect():
    report = load_report(UNSAFE)
    history = load_history(UNSAFE)

    assert_kill_report(
        report,
        mode="unsafe",
        effects=2,
        result="FAIL",
    )

    assert report["duplicate_suppressions"] == []

    assert {
        effect["fencing_token"]
        for effect in report["effects"]
    } == {1, 2}

    assert_original_execution_never_resumed(history)


def test_kill_post_commit_fencing_is_insufficient():
    report = load_report(FENCED)
    history = load_history(FENCED)

    assert_kill_report(
        report,
        mode="fenced",
        effects=2,
        result="FAIL",
    )

    assert report["duplicate_suppressions"] == []

    assert {
        effect["fencing_token"]
        for effect in report["effects"]
    } == {1, 2}

    assert_original_execution_never_resumed(history)


def test_kill_post_commit_idempotency_survives_crash():
    report = load_report(IDEMPOTENT)
    history = load_history(IDEMPOTENT)

    assert_kill_report(
        report,
        mode="idempotent",
        effects=1,
        result="PASS",
    )

    assert len(report["effects"]) == 1

    suppressions = report["duplicate_suppressions"]

    assert len(suppressions) == 1
    assert suppressions[0]["worker"] == "worker-b"
    assert suppressions[0]["fencing_token"] == 2
    assert suppressions[0]["type"] == "duplicate_suppressed"

    assert_original_execution_never_resumed(history)
