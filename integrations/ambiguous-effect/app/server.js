const http = require("http");
const { Pool } = require("pg");

const PORT = Number(
  process.env.PORT || "8080",
);

const DATABASE_URL =
  process.env.DATABASE_URL;

if (!DATABASE_URL) {
  throw new Error(
    "DATABASE_URL is required",
  );
}

const pool = new Pool({
  connectionString: DATABASE_URL,
});


async function readJson(req) {
  const chunks = [];

  for await (const chunk of req) {
    chunks.push(chunk);
  }

  const raw = Buffer
    .concat(chunks)
    .toString("utf8");

  return raw ? JSON.parse(raw) : {};
}


function sendJson(
  res,
  status,
  body,
) {
  const encoded = JSON.stringify(body);

  res.writeHead(
    status,
    {
      "content-type":
        "application/json",
      "content-length":
        Buffer.byteLength(encoded),
    },
  );

  res.end(encoded);
}


function validateCharge(data) {
  if (
    typeof data.job_id !== "string"
    || data.job_id.length === 0
  ) {
    throw new Error(
      "job_id must be a non-empty string",
    );
  }

  if (
    !Number.isInteger(data.amount)
    || data.amount <= 0
  ) {
    throw new Error(
      "amount must be a positive integer",
    );
  }
}


function requestIdentity(req) {
  const workerName =
    req.headers[
      "x-faultline-worker"
    ] || "external-client";

  const rawToken =
    req.headers[
      "x-faultline-token"
    ];

  const parsed =
    Number(rawToken);

  const fencingToken =
    Number.isInteger(parsed)
      ? parsed
      : 0;

  const fencingEnabled =
    req.headers[
      "x-faultline-fencing"
    ] === "enabled";

  return {
    workerName,
    fencingToken,
    fencingEnabled,
  };
}


async function recordEvent({
  jobId,
  workerName,
  fencingToken,
  eventType,
  details = {},
}) {
  await pool.query(
    `
      INSERT INTO service_events (
          job_id,
          worker_name,
          fencing_token,
          event_type,
          details
      )
      VALUES ($1, $2, $3, $4, $5::jsonb)
    `,
    [
      jobId,
      workerName,
      fencingToken,
      eventType,
      JSON.stringify(details),
    ],
  );
}


async function advanceFence(
  client,
  jobId,
  fencingToken,
) {
  if (
    !Number.isInteger(fencingToken)
    || fencingToken <= 0
  ) {
    throw new Error(
      "fencing requires a positive token",
    );
  }

  const result = await client.query(
    `
      INSERT INTO remote_ownership (
          job_id,
          current_token
      )
      VALUES ($1, $2)

      ON CONFLICT (job_id)
      DO UPDATE SET
          current_token = GREATEST(
              remote_ownership.current_token,
              EXCLUDED.current_token
          ),
          updated_at = NOW()

      RETURNING current_token
    `,
    [
      jobId,
      fencingToken,
    ],
  );

  return Number(
    result.rows[0].current_token,
  );
}


async function performCharge({
  data,
  workerName,
  fencingToken,
  fencingEnabled,
  idempotent,
}) {
  const client =
    await pool.connect();

  try {
    await client.query(
      "BEGIN",
    );

    let remoteToken = null;

    if (fencingEnabled) {
      remoteToken =
        await advanceFence(
          client,
          data.job_id,
          fencingToken,
        );

      if (
        fencingToken
        < remoteToken
      ) {
        await client.query(
          "COMMIT",
        );

        return {
          inserted: false,
          duplicate_suppressed:
            false,
          stale_rejected: true,
          remote_token:
            remoteToken,
          charge: null,
        };
      }
    }

    if (!idempotent) {
      const result =
        await client.query(
          `
            INSERT INTO charges (
                job_id,
                worker_name,
                fencing_token,
                amount,
                idempotency_key
            )
            VALUES (
                $1,
                $2,
                $3,
                $4,
                NULL
            )
            RETURNING *
          `,
          [
            data.job_id,
            workerName,
            fencingToken,
            data.amount,
          ],
        );

      await client.query(
        "COMMIT",
      );

      return {
        inserted: true,
        duplicate_suppressed:
          false,
        stale_rejected: false,
        remote_token:
          remoteToken,
        charge: result.rows[0],
      };
    }

    const key =
      data.idempotency_key
      || data.job_id;

    const inserted =
      await client.query(
        `
          INSERT INTO charges (
              job_id,
              worker_name,
              fencing_token,
              amount,
              idempotency_key
          )
          VALUES (
              $1,
              $2,
              $3,
              $4,
              $5
          )

          ON CONFLICT (
              idempotency_key
          )
          WHERE
              idempotency_key
              IS NOT NULL

          DO NOTHING

          RETURNING *
        `,
        [
          data.job_id,
          workerName,
          fencingToken,
          data.amount,
          key,
        ],
      );

    if (
      inserted.rowCount === 1
    ) {
      await client.query(
        "COMMIT",
      );

      return {
        inserted: true,
        duplicate_suppressed:
          false,
        stale_rejected: false,
        remote_token:
          remoteToken,
        charge:
          inserted.rows[0],
      };
    }

    const existing =
      await client.query(
        `
          SELECT *
          FROM charges
          WHERE idempotency_key = $1
        `,
        [key],
      );

    await client.query(
      "COMMIT",
    );

    return {
      inserted: false,
      duplicate_suppressed:
        true,
      stale_rejected: false,
      remote_token:
        remoteToken,
      charge:
        existing.rows[0],
    };

  } catch (error) {
    await client.query(
      "ROLLBACK",
    );

    throw error;

  } finally {
    client.release();
  }
}


const server = http.createServer(
  async (req, res) => {
    try {
      if (
        req.method === "GET"
        && req.url === "/health"
      ) {
        await pool.query(
          "SELECT 1",
        );

        sendJson(
          res,
          200,
          {
            status: "ok",
            database:
              "connected",
          },
        );

        return;
      }

      const unsafe =
        req.method === "POST"
        && req.url === "/charge";

      const idempotent =
        req.method === "POST"
        && req.url
          === "/charge-idempotent";

      if (
        !unsafe
        && !idempotent
      ) {
        sendJson(
          res,
          404,
          {
            error:
              "not_found",
          },
        );

        return;
      }

      const data =
        await readJson(req);

      validateCharge(data);

      const {
        workerName,
        fencingToken,
        fencingEnabled,
      } = requestIdentity(req);

      const mode =
        idempotent
          ? "idempotent"
          : "unsafe";

      await recordEvent({
        jobId: data.job_id,
        workerName,
        fencingToken,
        eventType:
          "effect_started",
        details: {
          mode,
          fencing:
            fencingEnabled,
        },
      });

      console.log(
        [
          "EFFECT_STARTED",
          `job=${data.job_id}`,
          `worker=${workerName}`,
          `token=${fencingToken}`,
          `mode=${mode}`,
          `fencing=${
            fencingEnabled
              ? 1
              : 0
          }`,
        ].join(" "),
      );

      const result =
        await performCharge({
          data,
          workerName,
          fencingToken,
          fencingEnabled,
          idempotent,
        });

      if (
        result.stale_rejected
      ) {
        await recordEvent({
          jobId: data.job_id,
          workerName,
          fencingToken,
          eventType:
            "stale_remote_rejected",
          details: {
            mode,
            remote_token:
              result.remote_token,
          },
        });

        console.log(
          [
            "STALE_REMOTE_REJECTED",
            `job=${data.job_id}`,
            `worker=${workerName}`,
            `token=${fencingToken}`,
            `current=${
              result.remote_token
            }`,
          ].join(" "),
        );

        sendJson(
          res,
          409,
          {
            ok: false,
            stale_rejected: true,
            remote_token:
              result.remote_token,
          },
        );

        return;
      }

      if (fencingEnabled) {
        await recordEvent({
          jobId: data.job_id,
          workerName,
          fencingToken,
          eventType:
            "fencing_accepted",
          details: {
            remote_token:
              result.remote_token,
          },
        });

        console.log(
          [
            "FENCING_ACCEPTED",
            `job=${data.job_id}`,
            `worker=${workerName}`,
            `token=${fencingToken}`,
            `current=${
              result.remote_token
            }`,
          ].join(" "),
        );
      }

      if (
        result
          .duplicate_suppressed
      ) {
        await recordEvent({
          jobId: data.job_id,
          workerName,
          fencingToken,
          eventType:
            "duplicate_suppressed",
          details: {
            mode,
            idempotency_key:
              result.charge
                .idempotency_key,
          },
        });

        console.log(
          [
            "DUPLICATE_SUPPRESSED",
            `job=${data.job_id}`,
            `worker=${workerName}`,
            `token=${fencingToken}`,
          ].join(" "),
        );

      } else {
        await recordEvent({
          jobId: data.job_id,
          workerName,
          fencingToken,
          eventType:
            "external_effect_committed",
          details: {
            mode,
            charge_id:
              result.charge.id,
          },
        });

        console.log(
          [
            "EFFECT_COMMITTED",
            `job=${data.job_id}`,
            `worker=${workerName}`,
            `token=${fencingToken}`,
            `charge_id=${
              result.charge.id
            }`,
          ].join(" "),
        );
      }

      const dropResponse =
        req.headers[
          "x-faultline-drop-response"
        ] === "after-commit";

      if (dropResponse) {
        await recordEvent({
          jobId: data.job_id,
          workerName,
          fencingToken,
          eventType:
            "response_dropped",
          details: {
            mode,
            fencing:
              fencingEnabled,
            after: "commit",
          },
        });

        console.log(
          [
            "RESPONSE_DROPPED",
            `job=${data.job_id}`,
            `worker=${workerName}`,
            `token=${fencingToken}`,
            "after=commit",
          ].join(" "),
        );

        res.destroy();

        return;
      }

      sendJson(
        res,
        result.inserted
          ? 201
          : 200,
        {
          ok: true,
          mode,
          fencing:
            fencingEnabled,
          ...result,
        },
      );

    } catch (error) {
      console.error(
        "REQUEST_ERROR",
        error,
      );

      if (
        !res.headersSent
        && !res.destroyed
      ) {
        sendJson(
          res,
          500,
          {
            error:
              error.message,
          },
        );
      }
    }
  },
);


server.listen(
  PORT,
  "0.0.0.0",
  () => {
    console.log(
      `CHARGE_SERVICE_READY port=${PORT}`,
    );
  },
);


async function shutdown() {
  server.close(
    async () => {
      await pool.end();
      process.exit(0);
    },
  );
}


process.on(
  "SIGTERM",
  shutdown,
);

process.on(
  "SIGINT",
  shutdown,
);
