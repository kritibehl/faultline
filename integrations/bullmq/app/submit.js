const { Queue } = require("bullmq");


function argument(name) {
  const index = process.argv.indexOf(name);

  if (
    index === -1 ||
    index + 1 >= process.argv.length
  ) {
    return null;
  }

  return process.argv[index + 1];
}


async function main() {
  const mode = argument("--mode");
  const jobId = argument("--job-id");
  const window =
    argument("--window") || "post-commit";

  if (
    mode !== "unsafe" &&
    mode !== "idempotent"
  ) {
    throw new Error(
      "mode must be unsafe or idempotent",
    );
  }

  if (!jobId) {
    throw new Error(
      "--job-id is required",
    );
  }

  if (window !== "post-commit") {
    throw new Error(
      "BullMQ supports only post-commit",
    );
  }

  const queue = new Queue(
    process.env.QUEUE_NAME ||
      "faultline-payments",
    {
      connection: {
        host:
          process.env.REDIS_HOST ||
          "redis",
        port: Number(
          process.env.REDIS_PORT ||
          "6379",
        ),
      },
    },
  );

  const job = await queue.add(
    "process-payment",
    {
      job_id: jobId,
      amount: 100,
      mode,
      window,
    },
    {
      jobId,
      removeOnComplete: false,
      removeOnFail: false,
    },
  );

  console.log(jobId);
  console.log(job.id);

  await queue.close();
}


main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
