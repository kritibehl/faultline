from services.worker.transport_db import _classify_sql


def test_claim_is_classified():
    sql = "SELECT id FROM jobs WHERE status = 'queued' FOR UPDATE SKIP LOCKED"
    assert _classify_sql(sql) == "claim"


def test_commit_is_classified():
    sql = "UPDATE jobs SET status = 'done', completed_at = now() WHERE id = %s"
    assert _classify_sql(sql) == "commit"
