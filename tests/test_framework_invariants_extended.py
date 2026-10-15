from faultline.invariants import (
    eventually_processed_after_recovery,
    no_lost_committed_effect,
    stale_owner_cannot_commit,
)


def test_stale_owner_cannot_commit_passes_with_no_accepted_stale_commits():
    result = stale_owner_cannot_commit(0)
    assert result.passed
    assert result.observed == 0 and result.limit == 0


def test_stale_owner_cannot_commit_fails_when_a_stale_commit_is_accepted():
    assert not stale_owner_cannot_commit(1).passed


def test_no_lost_committed_effect_passes_with_one_effect():
    assert no_lost_committed_effect(1).passed


def test_no_lost_committed_effect_fails_when_work_is_dropped():
    assert not no_lost_committed_effect(0).passed


def test_eventually_processed_after_recovery_passes_when_processed():
    assert eventually_processed_after_recovery(True).passed


def test_eventually_processed_after_recovery_fails_when_hung():
    assert not eventually_processed_after_recovery(False).passed
