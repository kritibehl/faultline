"""Audit actual PostgreSQL effect ownership, not misleading event order.

The Celery schema's BEFORE INSERT trigger reads job_ownership with FOR SHARE.
This serializes the captured ownership token against ownership UPDATEs until
commit, so a later worker claim cannot slip between the snapshot and commit.
Older report artifacts missing this snapshot are INCONCLUSIVE, never PASS.
"""
from __future__ import annotations

from typing import Any


def audit_effect_ownership(effects: list[dict[str, Any]]) -> dict[str, Any]:
    """Check each durable effect against ownership held at insertion commit.

    PASS means no *observed* accepted effect used the wrong owner token.
    FAIL means at least one accepted effect had a mismatched owner token.
    INCONCLUSIVE means some effect lacks trustworthy ownership evidence.
    This audits accepted effects, not worker attempts or broker ACKs.
    """
    if not isinstance(effects, list):
        return {
            "status": "INCONCLUSIVE", "reason": "effects are not a list",
            "effects_checked": 0, "stale_commits_accepted": None,
            "violations": [], "incomplete_evidence": [],
        }

    mismatches: list[dict[str, Any]] = []
    missing: list[int] = []
    stale = 0
    checked = 0

    for index, row in enumerate(effects):
        if not isinstance(row, dict):
            missing.append(index)
            continue
        presented = row.get("fencing_token")
        owner = row.get("owner_token_at_commit")
        if (not isinstance(presented, int) or isinstance(presented, bool)
                or not isinstance(owner, int) or isinstance(owner, bool)
                or presented <= 0 or owner <= 0):
            missing.append(index)
            continue
        checked += 1
        if presented != owner:
            if presented < owner:
                stale += 1
            mismatches.append({
                "effect_index": index,
                "worker": row.get("worker"),
                "presented_token": presented,
                "owner_token_at_commit": owner,
                "kind": "stale" if presented < owner else "invalid_future_token",
            })

    if mismatches:
        status = "FAIL"
        reason = "accepted effects did not match locked ownership at insertion"
    elif missing:
        status = "INCONCLUSIVE"
        reason = "effects lack authoritative commit-time ownership snapshots"
    else:
        status = "PASS"
        reason = "all accepted effects match their locked commit-time owner"

    return {
        "status": status,
        "reason": reason,
        "effects_checked": checked,
        "stale_commits_accepted": stale if not missing else None,
        "violations": mismatches,
        "incomplete_evidence": missing,
        "scope": "accepted PostgreSQL effects; not broker ACK or liveness",
    }
