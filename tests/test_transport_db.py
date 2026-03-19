from services.worker.transport_db import _classify_sql


def test_classify_claim_query():
    sql = "SELECT id FROM jobs WHERE status = 'queued' FOR UPDATE SKIP LOCKED"
    assert _classify_sql(sql) == "claim"


def test_classify_heartbeat_query():
    sql = "UPDATE jobs SET lease_expires_at = now() + interval '30 seconds' WHERE id = %s"
    assert _classify_sql(sql) == "heartbeat"


def test_classify_commit_query():
    sql = "UPDATE jobs SET status = 'done', completed_at = now() WHERE id = %s"
    assert _classify_sql(sql) == "commit"
