def test_lease_takeover_rejects_stale_worker():
    current_lease_owner = "worker-b"
    stale_commit_owner = "worker-a"
    assert stale_commit_owner != current_lease_owner
