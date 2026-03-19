from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class RemediationState:
    consecutive_transport_failures: int = 0
    quarantined_until: float = 0.0
    degraded_until: float = 0.0
    recent_partition_started_at: float | None = None
    partition_recovery_durations: list[float] = field(default_factory=list)

    def record_failure(self) -> None:
        self.consecutive_transport_failures += 1

    def record_success(self) -> None:
        self.consecutive_transport_failures = 0

    def enter_degraded_mode(self, seconds: float) -> None:
        self.degraded_until = max(self.degraded_until, time.time() + seconds)

    def quarantine(self, seconds: float) -> None:
        self.quarantined_until = max(self.quarantined_until, time.time() + seconds)

    def is_quarantined(self) -> bool:
        return time.time() < self.quarantined_until

    def is_degraded(self) -> bool:
        return time.time() < self.degraded_until

    def adaptive_backoff_seconds(self, base: float = 0.12, cap: float = 1.2) -> float:
        return min(cap, base * (2 ** max(0, self.consecutive_transport_failures - 1)))

    def note_partition_start(self) -> None:
        if self.recent_partition_started_at is None:
            self.recent_partition_started_at = time.time()

    def note_partition_recovered(self) -> float | None:
        if self.recent_partition_started_at is None:
            return None
        duration = time.time() - self.recent_partition_started_at
        self.partition_recovery_durations.append(duration)
        self.recent_partition_started_at = None
        return duration

    def median_partition_recovery_seconds(self) -> float:
        if not self.partition_recovery_durations:
            return 0.0
        values = sorted(self.partition_recovery_durations)
        n = len(values)
        mid = n // 2
        if n % 2 == 1:
            return values[mid]
        return (values[mid - 1] + values[mid]) / 2
