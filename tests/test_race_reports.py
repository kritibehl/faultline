from services.reporting.race_reports import build_race_report, explain_report


def test_build_race_report():
    artifact = {
        "job_id": "job-1",
        "worker_a_log": "claim started\\nlease acquired\\nstale write rejected\\n",
        "worker_b_log": "claim started\\ncommit accepted\\n",
        "final_state": {
            "state": "succeeded",
            "lease_owner": "worker-b",
            "fencing_token": 2,
            "attempts": 1,
        },
    }

    report = build_race_report(artifact)
    assert report["job_id"] == "job-1"
    assert report["final_state"]["state"] == "succeeded"


def test_explain_report():
    report = {
        "counters": {
            "worker-a": {"stale_write_blocked": 1},
            "worker-b": {"claim": 1},
        },
        "final_state": {"state": "succeeded", "fencing_token": 2},
    }

    explanation = explain_report(report)
    assert explanation["confidence"] in {"medium", "high"}
    assert "likely_cause" in explanation
