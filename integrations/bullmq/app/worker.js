const { Worker } = require("bullmq");

const {
  idempotentCommit,
  nextToken,
  recordAttempt,
  unsafeCommit,
} = require("./db");


const QUEUE_NAME =
  process.env.QUEUE_NAME ||
  "faultline-payments";

const WORKER_NAME =
  process.env.WORKER_NAME ||
  "unknown-worker";

const LOCK_DURATION_MS = Number(
  process.env.LOCK_DURATION_MS || "5000",
);

const STALLED_INTERVAL_MS = Number(
  process.env.STALLED_INTERVAL_MS || "1000",
);

const MAX_STALLED_COUNT = Number(
  process.env.MAX_STALLED_COUNT || "1",
);

const connection = {
  host: process.env.REDIS_HOST || "redis",
  port: Number(process.env.REDIS_PORT || "6379"),
};


function sleep(ms) {
  return new Promise(
    (resolve) => setTimeout(resolve, ms),
  );
}


const worker = new Worker(
  QUEUE_NAME,
  async (job) => {
    const {
      job_id: jobId,
      amount,
      mode,
      window,
    } = job.data;

    if (window !== "post-commit") {
      throw new Error(
        `unsupported window: ${window}`,
      );
    }

    if (
      mode !== "unsafe" &&
      mode !== "idempotent"
    ) {
      throw new Error(
        `unsupported mode: ${mode}`,
      );
    }

    const token = await nextToken(jobId);

    await recordAttempt(
      jobId,
      WORKER_NAME,
      token,
      "delivery_started",
    );

    console.log(
      `DELIVERY job=${jobId} ` +
      `worker=${WORKER_NAME} ` +
      `token=${token} ` +
      `mode=${mode} ` +
      `window=${window}`,
    );

    let committed;

    if (mode === "unsafe") {
      committed = await unsafeCommit(
        jobId,
        WORKER_NAME,
        token,
        amount,
      );
    } else {
      committed = await idempotentCommit(
        jobId,
        WORKER_NAME,
        token,
        amount,
      );
    }

    const phase = committed
      ? "commit_accepted"
      : "duplicate_suppressed";

    await recordAttempt(
      jobId,
      WORKER_NAME,
      token,
      phase,
    );

    console.log(
      `${phase.toUpperCase()} ` +
      `job=${jobId} ` +
      `worker=${WORKER_NAME} ` +
      `token=${token}`,
    );

    if (token === 1) {
      await recordAttempt(
        jobId,
        WORKER_NAME,
        token,
        "ready_after_commit",
      );

      console.log(
        `READY_AFTER_COMMIT ` +
        `job=${jobId} ` +
        `worker=${WORKER_NAME} ` +
        `token=${token}`,
      );

      await sleep(15000);

      await recordAttempt(
        jobId,
        WORKER_NAME,
        token,
        "post_commit_window_exit",
      );

      console.log(
        `POST_COMMIT_WINDOW_EXIT ` +
        `job=${jobId} ` +
        `worker=${WORKER_NAME} ` +
        `token=${token}`,
      );
    }

    return {
      job_id: jobId,
      worker: WORKER_NAME,
      token,
      committed,
    };
  },
  {
    connection,
    lockDuration: LOCK_DURATION_MS,
    stalledInterval: STALLED_INTERVAL_MS,
    maxStalledCount: MAX_STALLED_COUNT,
  },
);


worker.on("ready", () => {
  console.log(
    `WORKER_READY worker=${WORKER_NAME}`,
  );
});


worker.on("stalled", (jobId) => {
  console.log(
    `JOB_STALLED job=${jobId} ` +
    `worker=${WORKER_NAME} ` +
    `ts=${new Date().toISOString()}`,
  );
});


worker.on("failed", (job, error) => {
  console.log(
    `JOB_FAILED job=${job?.id || "unknown"} ` +
    `worker=${WORKER_NAME} ` +
    `error=${error.message}`,
  );
});


worker.on("error", (error) => {
  console.error(
    `WORKER_ERROR worker=${WORKER_NAME} ` +
    `error=${error.message}`,
  );
});
