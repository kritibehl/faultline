# PostgreSQL Schema Diagram

```text
+------------------+          +----------------------+
| jobs             |          | ledger_entries       |
+------------------+          +----------------------+
| id               |<-------->| job_id               |
| state            |          | fencing_token        |
| lease_owner      |          | committed_at         |
| lease_expires_at |          +----------------------+
| fencing_token    |
| next_run_at      |
| updated_at       |
+------------------+
Correctness boundary

The jobs.fencing_token column is the current ownership epoch.

A worker commit is valid only when:

submitted_fencing_token == jobs.fencing_token

ledger_entries records the protected commit path.
