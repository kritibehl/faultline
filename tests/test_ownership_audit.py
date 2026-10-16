"""Milestone 8 safety evidence regression tests."""
from pathlib import Path

import pytest

from faultline.invariants.ownership import audit_effect_ownership
from faultline.adapters import celery


def effect(presented=1, owner=1, worker="worker-a"):
    return {
        "worker": worker,
        "fencing_token": presented,
        "owner_token_at_commit": owner,
        "committed_at": "2026-10-16 04:26:28+00",
    }


def test_single_legitimate_commit_passes():
    assert audit_effect_ownership([effect()])["status"] == "PASS"


def test_commit_before_later_takeover_is_valid():
    # A's already committed token 1 is legitimate even when B later claims 2.
    assert audit_effect_ownership([effect(1, 1)])["status"] == "PASS"


def test_two_legitimate_commits_across_takeover_pass():
    result = audit_effect_ownership([effect(1, 1), effect(2, 2, "worker-b")])
    assert result["status"] == "PASS"
    assert result["effects_checked"] == 2


def test_stale_commit_accepted_after_takeover_fails():
    result = audit_effect_ownership([effect(1, 2)])
    assert result["status"] == "FAIL"
    assert result["stale_commits_accepted"] == 1
    assert result["violations"][0]["kind"] == "stale"


def test_stale_only_commit_cannot_false_pass():
    assert audit_effect_ownership([effect(1, 3)])["status"] == "FAIL"


def test_mismatched_future_token_fails():
    assert audit_effect_ownership([effect(2, 1)])["status"] == "FAIL"


def test_legacy_effect_without_snapshot_inconclusive():
    old = effect()
    old.pop("owner_token_at_commit")
    result = audit_effect_ownership([old])
    assert result["status"] == "INCONCLUSIVE"
    assert result["stale_commits_accepted"] is None


def test_one_good_one_missing_snapshot_inconclusive():
    result = audit_effect_ownership([effect(), effect(owner=None)])
    assert result["status"] == "INCONCLUSIVE"


def test_proven_violation_overrides_missing_evidence():
    result = audit_effect_ownership([effect(1, 2), effect(owner=None)])
    assert result["status"] == "FAIL"


def test_noninteger_snapshot_not_trusted():
    assert audit_effect_ownership([effect(owner="2")])["status"] == "INCONCLUSIVE"
    assert audit_effect_ownership([effect(owner=True)])["status"] == "INCONCLUSIVE"


def test_empty_effects_vacuous_safety():
    result = audit_effect_ownership([])
    assert result["status"] == "PASS"
    assert result["effects_checked"] == 0


def test_query_effects_parses_owner_snapshot(monkeypatch):
    monkeypatch.setattr(
        celery, "sql",
        lambda query: "worker-b\t2\t100\t2026-10-16 04:26:42+00\t2",
    )
    row = celery.query_effects("payment-test")[0]
    assert row["fencing_token"] == 2
    assert row["owner_token_at_commit"] == 2


def test_query_effects_marks_missing_snapshot(monkeypatch):
    monkeypatch.setattr(
        celery, "sql",
        lambda query: "worker-a\t1\t100\t2026-10-16 04:26:42+00\t",
    )
    assert celery.query_effects("payment-test")[0]["owner_token_at_commit"] is None


def test_schema_uses_transactional_owner_lock():
    schema = Path("integrations/celery/postgres/init.sql").read_text()
    assert "owner_token_at_commit" in schema
    assert "FOR SHARE" in schema
    assert "BEFORE INSERT ON effects" in schema
    assert "faultline_stamp_effect_owner" in schema
