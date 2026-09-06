const { Pool } = require("pg");

const DATABASE_URL =
  process.env.DATABASE_URL ||
  "postgresql://faultline:faultline@postgres:5432/faultline";

const pool = new Pool({
  connectionString: DATABASE_URL,
});

async function nextToken(jobId) {
  const result = await pool.query(
    `
    INSERT INTO job_ownership(job_id, current_token)
    VALUES ($1, 1)
    ON CONFLICT (job_id)
    DO UPDATE
    SET current_token = job_ownership.current_token + 1
    RETURNING current_token
    `,
    [jobId],
  );

  return Number(result.rows[0].current_token);
}

async function recordAttempt(
  jobId,
  workerName,
  token,
  phase,
) {
  await pool.query(
    `
    INSERT INTO attempts(
      job_id,
      worker_name,
      fencing_token,
      phase
    )
    VALUES ($1, $2, $3, $4)
    `,
    [
      jobId,
      workerName,
      token,
      phase,
    ],
  );
}

async function unsafeCommit(
  jobId,
  workerName,
  token,
  amount,
) {
  await pool.query(
    `
    INSERT INTO effects(
      job_id,
      worker_name,
      fencing_token,
      amount
    )
    VALUES ($1, $2, $3, $4)
    `,
    [
      jobId,
      workerName,
      token,
      amount,
    ],
  );

  return true;
}

async function idempotentCommit(
  jobId,
  workerName,
  token,
  amount,
) {
  const result = await pool.query(
    `
    INSERT INTO effects(
      job_id,
      worker_name,
      fencing_token,
      amount,
      idempotency_key
    )
    VALUES ($1, $2, $3, $4, $5)
    ON CONFLICT (idempotency_key)
    WHERE idempotency_key IS NOT NULL
    DO NOTHING
    RETURNING id
    `,
    [
      jobId,
      workerName,
      token,
      amount,
      jobId,
    ],
  );

  return result.rowCount === 1;
}

async function closeDatabase() {
  await pool.end();
}

module.exports = {
  closeDatabase,
  idempotentCommit,
  nextToken,
  recordAttempt,
  unsafeCommit,
};
