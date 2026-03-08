"""
services/worker/invariants.py
Formal invariant checker for Faultline correctness guarantees.
"""
import psycopg2
from dataclasses import dataclass
from typing import List

@dataclass
class InvariantViolation:
    invariant: str
    job_id: str
    detail: str
    def __str__(self):
        return f"[{self.invariant}] job={self.job_id} — {self.detail}"

def _conn(database_url):
    return psycopg2.connect(database_url)

def check_i2_no_duplicate_side_effect(cur, job_ids) -> List[InvariantViolation]:
    violations = []
    cur.execute(
        "SELECT job_id, COUNT(*) FROM ledger_entries WHERE job_id=ANY(%s::uuid[]) GROUP BY job_id HAVING COUNT(*)>1",
        (job_ids,),
    )
    for job_id, cnt in cur.fetchall():
        violations.append(InvariantViolation("I2", str(job_id), f"{cnt} ledger entries — duplicate execution"))
    return violations

def check_i5_single_owner(cur, job_ids) -> List[InvariantViolation]:
    violations = []
    cur.execute(
        "SELECT id, lease_owner, lease_expires_at FROM jobs WHERE id=ANY(%s::uuid[]) AND state='running' AND lease_expires_at < NOW()",
        (job_ids,),
    )
    for job_id, owner, expires_at in cur.fetchall():
        violations.append(InvariantViolation("I5", str(job_id), f"stuck running with expired lease: owner={owner}"))
    return violations

def check_all(database_url: str, job_ids: list) -> List[InvariantViolation]:
    violations = []
    with _conn(database_url) as conn:
        with conn.cursor() as cur:
            violations += check_i2_no_duplicate_side_effect(cur, job_ids)
            violations += check_i5_single_owner(cur, job_ids)
    return violations

def assert_all(database_url: str, job_ids: list) -> None:
    violations = check_all(database_url, job_ids)
    if violations:
        raise AssertionError("Invariant violations:\n" + "\n".join(str(v) for v in violations))
