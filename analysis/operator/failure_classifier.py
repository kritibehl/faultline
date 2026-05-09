from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


FailureFamily = Literal[
    "stale_worker_race",
    "retry_storm",
    "coordination_contention",
    "starvation_risk",
    "lease_reclaim_loop",
    "unknown",
]


@dataclass(slots=True)
class FailureSignal:
    failure_family: FailureFamily
    severity: str
    safe_to_operate: bool
    reason: str
    recommended_action: str


def classify_failure(metrics: dict) -> FailureSignal:
    stale_rejections = int(metrics.get("stale_write_rejected_total", 0))
    retries = int(metrics.get("retry_total", 0))
    lease_takeovers = int(metrics.get("lease_takeover_total", 0))
    duplicate_commits = int(metrics.get("duplicate_commit_total", 0))
    claim_latency_ms = float(metrics.get("claim_latency_ms", 0.0))
    starvation_events = int(metrics.get("starvation_events", 0))

    if duplicate_commits > 0:
        return FailureSignal(
            failure_family="stale_worker_race",
            severity="critical",
            safe_to_operate=False,
            reason="duplicate commits detected in protected path",
            recommended_action="halt rollout and inspect fencing-token commit boundary",
        )

    if stale_rejections > 0 and lease_takeovers > 0:
        return FailureSignal(
            failure_family="stale_worker_race",
            severity="high",
            safe_to_operate=True,
            reason="stale workers attempted commits but fencing-token validation rejected them",
            recommended_action="review lease duration and worker pause behavior",
        )

    if retries >= 10:
        return FailureSignal(
            failure_family="retry_storm",
            severity="high",
            safe_to_operate=False,
            reason="retry volume suggests repeated execution instability",
            recommended_action="increase retry backoff and inspect downstream dependency health",
        )

    if lease_takeovers >= 10:
        return FailureSignal(
            failure_family="lease_reclaim_loop",
            severity="medium",
            safe_to_operate=False,
            reason="frequent lease takeovers indicate workers are not completing within lease window",
            recommended_action="increase lease duration or investigate worker execution latency",
        )

    if claim_latency_ms >= 100:
        return FailureSignal(
            failure_family="coordination_contention",
            severity="medium",
            safe_to_operate=True,
            reason="claim latency suggests coordinator contention",
            recommended_action="evaluate batch size and polling interval",
        )

    if starvation_events > 0:
        return FailureSignal(
            failure_family="starvation_risk",
            severity="medium",
            safe_to_operate=True,
            reason="mixed workload starvation detected",
            recommended_action="reduce batch size or add fairness-aware scheduling",
        )

    return FailureSignal(
        failure_family="unknown",
        severity="low",
        safe_to_operate=True,
        reason="no correctness-impacting failure signal detected",
        recommended_action="continue monitoring",
    )
