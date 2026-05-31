from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PoisonJob:
    job_id: str
    failure_reason: str
    retry_count: int
    recoverable: bool


@dataclass
class DeadLetterQueue:
    failed_jobs: list[PoisonJob] = field(default_factory=list)
    recovered: list[str] = field(default_factory=list)
    manual_review: list[str] = field(default_factory=list)

    def add_failed_job(self, job: PoisonJob) -> None:
        self.failed_jobs.append(job)

    def replay(self) -> dict[str, int]:
        for job in self.failed_jobs:
            if job.recoverable:
                self.recovered.append(job.job_id)
            else:
                self.manual_review.append(job.job_id)

        return {
            "failed_jobs": len(self.failed_jobs),
            "recovered": len(self.recovered),
            "manual_review": len(self.manual_review),
        }


def run_dlq_demo() -> dict[str, int]:
    dlq = DeadLetterQueue()

    for i in range(24):
        dlq.add_failed_job(
            PoisonJob(
                job_id=f"job-recoverable-{i}",
                failure_reason="transient_dependency_timeout",
                retry_count=3,
                recoverable=True,
            )
        )

    for i in range(3):
        dlq.add_failed_job(
            PoisonJob(
                job_id=f"job-manual-{i}",
                failure_reason="invalid_payload_or_permanent_failure",
                retry_count=5,
                recoverable=False,
            )
        )

    return dlq.replay()


if __name__ == "__main__":
    print(run_dlq_demo())
