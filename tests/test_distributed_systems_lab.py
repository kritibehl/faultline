from benchmark_lab.benchmark_comparison import run as run_benchmark
from governance.release_readiness import run as run_governance
from capacity_lab.capacity_simulator import run as run_capacity


def test_correctness_benchmark_lab_compares_strategies():
    result = run_benchmark()

    assert result["best_strategy"] == "lease_fencing"
    fencing = [x for x in result["comparison"] if x["strategy"] == "lease_fencing"][0]
    assert fencing["duplicate_rate"] == 0.0
    assert fencing["stale_write_rate"] == 0.0
    assert fencing["consistency_failures"] == 0


def test_reliability_governance_center_passes_release_readiness():
    result = run_governance()

    assert result["consistency_score"] == 99
    assert result["duplicate_risk"] == 0
    assert result["recovery_score"] == 95
    assert result["release_readiness"] == "PASS"
    assert result["architecture_maturity"]["idempotency"] == "PASS"


def test_capacity_lab_models_1000_worker_contention():
    result = run_capacity()

    profiles = {item["workers"]: item for item in result["profiles"]}
    assert 1000 in profiles
    assert profiles[1000]["lease_contention_events"] == 410
    assert profiles[1000]["retry_amplification"] == 8.9
