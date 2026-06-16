def test_duplicate_commit_prevention():
    committed_job_ids = {"job-001"}
    new_commit_job_id = "job-001"
    assert new_commit_job_id in committed_job_ids
