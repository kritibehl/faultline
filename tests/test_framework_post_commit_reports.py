import json
from pathlib import Path


CANONICAL = Path("artifacts/canonical")

UNSAFE = CANONICAL / "celery-post-commit-unsafe"
FENCED = CANONICAL / "celery-post-commit-fenced"
IDEMPOTENT = CANONICAL / "celery-post-commit-idempotent"


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


def appears_in_order(
    history: list[dict],
    expected: list[tuple[str, str]],
) -> bool:
    cursor = 0

    for event in history:
        pair = (
            event["worker"],
            event["type"],
        )

        if pair == expected[cursor]:
            cursor += 1

            if cursor == len(expected):
                return True

    return False


def assert_common_post_commit(
    report: dict,
    *,
    mode: str,
    committed_effects: int,
    result: str,
) -> None:
    assert report["framework"] == "faultline"
    assert report["adapter"] == "celery"
    assert report["mode"] == mode
    assert report["window"] == "post-commit"

    assert report["fault"] == "pause"
    assert report["fault_injection"] == {
        "inject": "SIGSTOP",
        "recover": "SIGCONT",
    }

    assert report["invariant"] == "at-most-one-effect"
    assert report["invariant_limit"] == 1
    assert report["invariant_observed"] == committed_effects

    assert report["committed_effects"] == committed_effects
    assert report["current_fencing_token"] == 2
    assert report["stale_rejections"] == []
    assert report["result"] == result


def test_post_commit_unsafe_duplicates_effect():
    report = load_report(UNSAFE)
    history = load_history(UNSAFE)

    assert_common_post_commit(
        report,
        mode="unsafe",
        committed_effects=2,
        result="FAIL",
    )

    assert report["duplicate_suppressions"] == []

    tokens = {
        effect["fencing_token"]
        for effect in report["effects"]
    }

    assert tokens == {1, 2}

    assert appears_in_order(
        history,
        [
            ("worker-a", "delivery_started"),
            ("worker-a", "commit_accepted"),
            ("worker-a", "ready_after_commit"),
            ("worker-a", "fault_injected"),
            ("worker-b", "delivery_started"),
            ("worker-b", "commit_accepted"),
            ("worker-b", "ownership_observed"),
            ("worker-a", "fault_recovered"),
            ("worker-a", "post_commit_window_exit"),
        ],
    )


def test_post_commit_fencing_is_insufficient():
    report = load_report(FENCED)
    history = load_history(FENCED)

    assert_common_post_commit(
        report,
        mode="fenced",
        committed_effects=2,
        result="FAIL",
    )

    assert report["duplicate_suppressions"] == []

    tokens = {
        effect["fencing_token"]
        for effect in report["effects"]
    }

    assert tokens == {1, 2}

    assert appears_in_order(
        history,
        [
            ("worker-a", "delivery_started"),
            ("worker-a", "commit_accepted"),
            ("worker-a", "ready_after_commit"),
            ("worker-a", "fault_injected"),
            ("worker-b", "delivery_started"),
            ("worker-b", "commit_accepted"),
            ("worker-b", "ownership_observed"),
            ("worker-a", "fault_recovered"),
            ("worker-a", "post_commit_window_exit"),
        ],
    )


def test_post_commit_idempotency_suppresses_redelivery():
    report = load_report(IDEMPOTENT)
    history = load_history(IDEMPOTENT)

    assert_common_post_commit(
        report,
        mode="idempotent",
        committed_effects=1,
        result="PASS",
    )

    assert len(report["effects"]) == 1

    suppression = report["duplicate_suppressions"]

    assert len(suppression) == 1
    assert suppression[0]["worker"] == "worker-b"
    assert suppression[0]["fencing_token"] == 2
    assert suppression[0]["type"] == "duplicate_suppressed"

    assert appears_in_order(
        history,
        [
            ("worker-a", "delivery_started"),
            ("worker-a", "commit_accepted"),
            ("worker-a", "ready_after_commit"),
            ("worker-a", "fault_injected"),
            ("worker-b", "delivery_started"),
            ("worker-b", "duplicate_suppressed"),
            ("worker-b", "ownership_observed"),
            ("worker-a", "fault_recovered"),
            ("worker-a", "post_commit_window_exit"),
        ],
    )
