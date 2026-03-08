#!/usr/bin/env python3
"""Drain all queued jobs except s12a/b/c — used by S12 drill."""
import os
import psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute(
    "UPDATE jobs SET state='succeeded' "
    "WHERE state='queued' "
    "AND (idempotency_key NOT LIKE 's12%' OR idempotency_key IS NULL)"
)
print(f"drained: {cur.rowcount} leftover jobs")
conn.commit()
conn.close()
