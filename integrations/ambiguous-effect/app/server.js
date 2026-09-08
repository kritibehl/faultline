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

async function unsafeCharge(data) {
  const result = await pool.query(
    `
      INSERT INTO charges (
          job_id,
          amount,
          idempotency_key
      )
      VALUES ($1, $2, NULL)
      RETURNING
          id,
          job_id,
          amount,
          committed_at
    `,
    [
      data.job_id,
      data.amount,
    ],
  );

  return {
    inserted: true,
    duplicate_suppressed: false,
    charge: result.rows[0],
  };
}

async function idempotentCharge(data) {
  const key =
    data.idempotency_key
    || data.job_id;

  const result = await pool.query(
    `
      INSERT INTO charges (
          job_id,
          amount,
          idempotency_key
      )
      VALUES ($1, $2, $3)
      ON CONFLICT (idempotency_key)
      WHERE idempotency_key IS NOT NULL
      DO NOTHING
      RETURNING
          id,
          job_id,
          amount,
          idempotency_key,
          committed_at
    `,
    [
      data.job_id,
      data.amount,
      key,
    ],
  );

  if (result.rowCount === 1) {
    return {
      inserted: true,
      duplicate_suppressed: false,
      charge: result.rows[0],
    };
  }

  const existing =
    await pool.query(
      `
        SELECT
            id,
            job_id,
            amount,
            idempotency_key,
            committed_at
        FROM charges
        WHERE idempotency_key = $1
      `,
      [
        key,
      ],
    );

  return {
    inserted: false,
    duplicate_suppressed: true,
    charge: existing.rows[0],
  };
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
            database: "connected",
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

      if (!unsafe && !idempotent) {
        sendJson(
          res,
          404,
          {
            error: "not_found",
          },
        );

        return;
      }

      const data =
        await readJson(req);

      validateCharge(data);

      const mode =
        idempotent
          ? "idempotent"
          : "unsafe";

      console.log(
        [
          "EFFECT_STARTED",
          `job=${data.job_id}`,
          `mode=${mode}`,
        ].join(" "),
      );

      const result =
        idempotent
          ? await idempotentCharge(data)
          : await unsafeCharge(data);

      if (
        result.duplicate_suppressed
      ) {
        console.log(
          [
            "DUPLICATE_SUPPRESSED",
            `job=${data.job_id}`,
            `mode=${mode}`,
          ].join(" "),
        );
      } else {
        console.log(
          [
            "EFFECT_COMMITTED",
            `job=${data.job_id}`,
            `mode=${mode}`,
            `charge_id=${result.charge.id}`,
          ].join(" "),
        );
      }

      const dropResponse =
        req.headers[
          "x-faultline-drop-response"
        ] === "after-commit";

      if (dropResponse) {
        console.log(
          [
            "RESPONSE_DROPPED",
            `job=${data.job_id}`,
            `mode=${mode}`,
            "after=commit",
          ].join(" "),
        );

        req.socket.destroy();

        return;
      }

      sendJson(
        res,
        result.inserted ? 201 : 200,
        {
          ok: true,
          mode,
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
            error: error.message,
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
