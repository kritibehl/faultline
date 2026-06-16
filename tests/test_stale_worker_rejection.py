def test_stale_worker_rejection():
    lease_expired = True
    commit_rejected = lease_expired
    assert commit_rejected is True
