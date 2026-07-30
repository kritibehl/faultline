from scripts.correctness_demo import (
    EXPECTED_DUPLICATE_DELIVERIES_SUPPRESSED,
    SCENARIO_COUNT,
    JobState,
    attempt_commit,
    deliver_effect,
    run_scenario,
)


def test_stale_worker_is_rejected_after_takeover():
    state = JobState(current_token=8)

    assert attempt_commit(state, presented_token=7) is False
    assert state.committed_token is None
    assert state.outbox_events == 0


def test_current_worker_commits_once_with_one_outbox_event():
    state = JobState(current_token=8)

    assert attempt_commit(state, presented_token=8) is True
    assert attempt_commit(state, presented_token=8) is False
    assert state.committed_token == 8
    assert state.outbox_events == 1


def test_duplicate_delivery_is_suppressed():
    state = JobState(current_token=8)

    assert deliver_effect(state, "job-123:completed") is True
    assert deliver_effect(state, "job-123:completed") is False


def test_all_deterministic_scenarios_preserve_invariants():
    assert SCENARIO_COUNT >= 1_500
    assert EXPECTED_DUPLICATE_DELIVERIES_SUPPRESSED == 37

    for index in range(SCENARIO_COUNT):
        duplicate_commits, lost_events, _ = run_scenario(index)

        assert duplicate_commits == 0
        assert lost_events == 0
