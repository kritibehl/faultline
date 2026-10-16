"""Boundary tests for independent safety and recovery properties."""

import pytest

from faultline.invariants.effects import (
    eventually_processed_after_recovery,
    no_lost_committed_effect,
    stale_owner_cannot_commit,
)


@pytest.mark.parametrize(
    ("accepted_stale_commits", "expected"),
    [
        (0, True),
        (1, False),
        (3, False),
    ],
)
def test_stale_owner_cannot_commit(
    accepted_stale_commits, expected
):
    result = stale_owner_cannot_commit(
        accepted_stale_commits
    )

    assert result.name == "stale-owner-cannot-commit"
    assert result.passed is expected
    assert result.observed == accepted_stale_commits
    assert result.limit == 0


@pytest.mark.parametrize(
    ("committed_effects", "expected"),
    [
        (0, False),
        (1, True),
        (2, True),
    ],
)
def test_no_lost_committed_effect(
    committed_effects, expected
):
    result = no_lost_committed_effect(
        committed_effects
    )

    assert result.name == "no-lost-committed-effect"
    assert result.passed is expected
    assert result.observed == committed_effects
    assert result.limit == 1


@pytest.mark.parametrize(
    ("recovered", "expected"),
    [
        (False, False),
        (True, True),
    ],
)
def test_eventually_processed_after_recovery(
    recovered, expected
):
    result = eventually_processed_after_recovery(
        recovered
    )

    assert (
        result.name
        == "eventually-processed-after-recovery"
    )
    assert result.passed is expected
    assert result.observed == int(recovered)
    assert result.limit == 1
