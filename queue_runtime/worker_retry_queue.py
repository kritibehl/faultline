from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RetryQueue:
    pending: list[str] = field(default_factory=list)
    dead_letter: list[str] = field(default_factory=list)
    max_retries: int = 3

    def schedule_retry(self, job_id: str, retry_count: int) -> None:
        if retry_count >= self.max_retries:
            self.dead_letter.append(job_id)
        else:
            self.pending.append(job_id)

    def pop_next(self) -> str | None:
        if not self.pending:
            return None
        return self.pending.pop(0)
