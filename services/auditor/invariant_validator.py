"""
Invariant validation and correctness scoring for Faultline++.

This layer turns correctness reasoning into operator-visible output:
- invariant checks
- near-miss detection
- correctness score
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class InvariantSnapshot:
    duplicate_commits: int
    stale_write_rejections: int
    jobs_stuck_running: int
    reconciled_jobs: int
    lease_reclaims: int
    total_runs: int


@dataclass(slots=True)
class ValidationResult:
    score: int
    status: str
    violations: list[str]
    near_misses: list[str]
    recommendations: list[str]


def validate_invariants(snapshot: InvariantSnapshot) -> ValidationResult:
    violations: list[str] = []
    near_misses: list[str] = []
    recommendations: list[str] = []

    score = 100

    if snapshot.duplicate_commits > 0:
        violations.append(f"duplicate_commits={snapshot.duplicate_commits}")
        score -= min(60, snapshot.duplicate_commits * 10)
        recommendations.append("Investigate stale-commit path; duplicate side effects violate the protected execution contract.")

    if snapshot.jobs_stuck_running > 0:
        violations.append(f"jobs_stuck_running={snapshot.jobs_stuck_running}")
        score -= min(20, snapshot.jobs_stuck_running * 2)
        recommendations.append("Review reaper / reconciler convergence and lease sizing.")

    if snapshot.lease_reclaims > max(1, snapshot.total_runs // 10):
        near_misses.append(f"high_lease_reclaims={snapshot.lease_reclaims}")
        score -= 5
        recommendations.append("Consider larger leases or adaptive tuning for slower workloads.")

    if snapshot.reconciled_jobs > 0:
        near_misses.append(f"reconciled_jobs={snapshot.reconciled_jobs}")
        score -= 3
        recommendations.append("Partial-failure windows are being recovered; review commit/update boundary.")

    if snapshot.stale_write_rejections == 0:
        near_misses.append("no_stale_write_rejections_observed")
        recommendations.append("Run fault-injection drills to continuously validate stale-worker protection.")

    status = "excellent"
    if violations:
        status = "violation-detected"
    elif score < 90:
        status = "review-recommended"

    return ValidationResult(
        score=max(0, score),
        status=status,
        violations=violations,
        near_misses=near_misses,
        recommendations=recommendations,
    )
