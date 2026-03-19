from services.worker.network_profiles import DNSFailure, NetworkFaultInjector
from services.worker.remediation import RemediationState


def test_dns_failure_profile_raises_on_connect():
    injector = NetworkFaultInjector(profile="dns_failure", seed=1)
    try:
        injector.before_operation("connect")
        assert False, "expected DNSFailure"
    except DNSFailure:
        assert True


def test_remediation_enters_degraded_mode_and_backoff_grows():
    state = RemediationState()
    state.record_failure()
    state.record_failure()
    state.enter_degraded_mode(5)
    assert state.is_degraded()
    state.record_failure()
    state.record_failure()
    assert state.adaptive_backoff_seconds() >= 2.0
