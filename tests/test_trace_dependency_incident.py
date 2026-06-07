from trace_explorer.trace_journey import generate_trace_explorer
from service_dependency_graph.generate_dependency_graph import generate
from incident_timeline.reconstruct_incident import reconstruct


def test_trace_explorer_generates_service_journey():
    result = generate_trace_explorer()

    assert result["trace_id"] == "trace-faultline-001"
    assert result["span_count"] == 6
    assert "producer_api" in result["service_path"]
    assert "postgres" in result["service_path"]
    assert result["root_cause_signal"]["decision"] == "reject_stale_write"


def test_service_dependency_graph_has_upstream_downstream():
    result = generate()

    assert "producer_api" in result["upstream"]
    assert "postgres" in result["downstream"]
    assert "outbox" in result["downstream"]
    assert result["failure_blast_radius"]["postgres_unavailable"] == "pause unsafe commits or fail closed"


def test_incident_timeline_reconstructs_root_cause_and_recovery():
    result = reconstruct()

    assert result["failure"] == "stale_worker_late_commit"
    assert result["root_cause"] == "worker resumed after lease ownership advanced"
    assert result["final_state"] == "consistent"
    assert any(event["event"] == "stale_commit_rejected" for event in result["events"])
