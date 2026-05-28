from home_protocol_lab.simulate_home_protocol import run_all


def test_home_protocol_lab_passes_all_scenarios():
    result = run_all()

    assert result["passed"] == 8
    assert result["total"] == 8
    assert result["all_passed"] is True


def test_home_protocol_lab_contains_network_degradation():
    result = run_all()
    scenarios = {item["scenario"] for item in result["results"]}

    assert "network_degradation" in scenarios


def test_home_protocol_lab_contains_multi_hub_failover():
    result = run_all()
    scenarios = {item["scenario"] for item in result["results"]}

    assert "primary_secondary_failover" in scenarios
    assert "hub_rejoin_reconciliation" in scenarios
