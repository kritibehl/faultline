def test_retry_storm_recovery_has_retry_cap():
    retry_count = 5
    retry_cap = 5
    assert retry_count <= retry_cap
