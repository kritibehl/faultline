from pathlib import Path

from outbox.replay_test import run_outbox_demo
from saga.saga_simulator import run_saga_demo


def test_transactional_outbox_replay_report():
    result = run_outbox_demo()

    assert result["events_written"] == 500
    assert result["duplicates_prevented"] == 37
    assert result["lost_events"] == 0
    assert result["idempotency_violations"] == 0


def test_saga_compensation_workflow_returns_consistent_state():
    result = run_saga_demo()

    assert result["workflow"] == "payment_inventory_shipping"
    assert result["failed_step"] == "shipping_label"
    assert result["compensations_executed"] == ["refund_payment", "release_inventory"]
    assert result["final_state"] == "consistent"


def test_inspector_ui_artifacts_exist():
    assert Path("inspector_ui/leases_timeline.html").exists()
    assert Path("inspector_ui/stale_worker_rejection.svg").exists()
    assert Path("inspector_ui/duplicate_risk_panel.svg").exists()
