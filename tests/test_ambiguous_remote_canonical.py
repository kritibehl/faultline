from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(
    "artifacts/canonical"
)


def load(
    strategy: str,
) -> dict[str, object]:
    path = (
        ROOT
        / (
            "celery-ambiguous-remote-"
            + strategy
        )
        / "report.json"
    )

    return json.loads(
        path.read_text()
    )


def test_ambiguous_remote_matrix():
    naive = load("naive")
    fencing = load("fencing")
    idem = load("idempotency")
    both = load(
        "fencing-idempotency"
    )

    assert (
        naive["external_effects"]
        == 2
    )
    assert (
        naive[
            "duplicate_suppressions"
        ]
        == 0
    )
    assert naive["result"] == "FAIL"

    assert (
        fencing["external_effects"]
        == 2
    )
    assert (
        fencing[
            "duplicate_suppressions"
        ]
        == 0
    )
    assert (
        fencing[
            "remote_fencing_acceptances"
        ]
        == 2
    )
    assert (
        fencing[
            "remote_fencing_token"
        ]
        == 2
    )
    assert (
        fencing[
            "remote_stale_rejections"
        ]
        == 0
    )
    assert (
        fencing["result"]
        == "FAIL"
    )

    assert (
        idem["external_effects"]
        == 1
    )
    assert (
        idem[
            "duplicate_suppressions"
        ]
        == 1
    )
    assert idem["result"] == "PASS"

    assert (
        both["external_effects"]
        == 1
    )
    assert (
        both[
            "duplicate_suppressions"
        ]
        == 1
    )
    assert (
        both[
            "remote_fencing_acceptances"
        ]
        == 2
    )
    assert (
        both[
            "remote_fencing_token"
        ]
        == 2
    )
    assert (
        both[
            "remote_stale_rejections"
        ]
        == 0
    )
    assert both["result"] == "PASS"
