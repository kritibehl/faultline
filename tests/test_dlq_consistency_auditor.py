from dlq.dead_letter_queue import run_dlq_demo
from consistency_auditor.nightly_audit import demo_clean_audit, demo_dirty_audit


def test_dead_letter_queue_recovery_report():
    result = run_dlq_demo()

    assert result["failed_jobs"] == 27
    assert result["recovered"] == 24
    assert result["manual_review"] == 3


def test_clean_consistency_audit_has_no_findings():
    result = demo_clean_audit()

    assert result["total_findings"] == 0
    assert result["orphan_events"] == []
    assert result["orphan_outbox_events"] == []
    assert result["duplicate_outbox_keys"] == []
    assert result["inconsistent_completed_jobs"] == []


def test_dirty_consistency_audit_finds_orphans_duplicates_and_missing_completion():
    result = demo_dirty_audit()

    assert result["total_findings"] == 4
    assert result["orphan_events"] == ["evt-orphan"]
    assert result["orphan_outbox_events"] == ["out-orphan"]
    assert result["duplicate_outbox_keys"] == ["idem-1"]
    assert result["inconsistent_completed_jobs"] == ["job-2"]
