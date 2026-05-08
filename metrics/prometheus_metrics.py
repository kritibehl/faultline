from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter


@dataclass
class FaultlineMetrics:
    duplicate_commit_total: int = 0
    stale_write_rejected_total: int = 0
    lease_takeover_total: int = 0
    retry_total: int = 0
    claim_latency_ms: list[float] = field(default_factory=list)
    commit_latency_ms: list[float] = field(default_factory=list)

    def observe_claim_latency(self, ms: float) -> None:
        self.claim_latency_ms.append(ms)

    def observe_commit_latency(self, ms: float) -> None:
        self.commit_latency_ms.append(ms)

    def render_prometheus(self) -> str:
        claim_avg = sum(self.claim_latency_ms) / len(self.claim_latency_ms) if self.claim_latency_ms else 0.0
        commit_avg = sum(self.commit_latency_ms) / len(self.commit_latency_ms) if self.commit_latency_ms else 0.0

        return "\n".join([
            "# HELP faultline_duplicate_commit_total Duplicate commit attempts observed",
            "# TYPE faultline_duplicate_commit_total counter",
            f"faultline_duplicate_commit_total {self.duplicate_commit_total}",
            "# HELP faultline_stale_write_rejected_total Stale writes rejected by fencing-token validation",
            "# TYPE faultline_stale_write_rejected_total counter",
            f"faultline_stale_write_rejected_total {self.stale_write_rejected_total}",
            "# HELP faultline_lease_takeover_total Lease takeovers after expiry",
            "# TYPE faultline_lease_takeover_total counter",
            f"faultline_lease_takeover_total {self.lease_takeover_total}",
            "# HELP faultline_retry_total Job retries scheduled",
            "# TYPE faultline_retry_total counter",
            f"faultline_retry_total {self.retry_total}",
            "# HELP faultline_claim_latency_ms Average claim latency in milliseconds",
            "# TYPE faultline_claim_latency_ms gauge",
            f"faultline_claim_latency_ms {claim_avg:.4f}",
            "# HELP faultline_commit_latency_ms Average commit latency in milliseconds",
            "# TYPE faultline_commit_latency_ms gauge",
            f"faultline_commit_latency_ms {commit_avg:.4f}",
        ]) + "\n"


class Timer:
    def __init__(self):
        self.start = perf_counter()

    def elapsed_ms(self) -> float:
        return (perf_counter() - self.start) * 1000.0
