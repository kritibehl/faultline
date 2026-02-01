-- 004_add_ledger_entries.sql
-- Payments-grade idempotency boundary for Faultline: one ledger entry per job

BEGIN;

CREATE TABLE IF NOT EXISTS ledger_entries (
  entry_id      BIGSERIAL PRIMARY KEY,
  job_id        UUID NOT NULL UNIQUE,
  account_id    TEXT NOT NULL,
  delta         BIGINT NOT NULL,
  created_at    TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ledger_entries_account
  ON ledger_entries(account_id);

COMMIT;
