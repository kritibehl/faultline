from faultline.scenarios import (
    ambiguous_remote,
)


def test_supported_strategies_are_exact():
    assert (
        ambiguous_remote.STRATEGIES
        == (
            "naive",
            "fencing",
            "idempotency",
            "fencing-idempotency",
        )
    )


def test_timestamp_key_accepts_postgres_and_iso():
    from faultline.history import (
        HistoryEvent,
    )

    postgres = HistoryEvent(
        ts="2026-09-07 23:00:00+00",
        type="a",
        job_id="job",
    )

    iso = HistoryEvent(
        ts="2026-09-07T23:00:01Z",
        type="b",
        job_id="job",
    )

    assert (
        ambiguous_remote.timestamp_key(
            postgres
        )
        <
        ambiguous_remote.timestamp_key(
            iso
        )
    )
