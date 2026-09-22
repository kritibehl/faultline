from __future__ import annotations
 
from dataclasses import dataclass
 
 
@dataclass(frozen=True)
class InvariantResult:
    name: str
    passed: bool
    observed: int
    limit: int
 
 
def at_most_one_effect(
    committed_effects: int,
) -> InvariantResult:
    return InvariantResult(
        name="at-most-one-effect",
        passed=committed_effects <= 1,
        observed=committed_effects,
        limit=1,
    )
 
 
def stale_owner_cannot_commit(
    stale_commits_accepted: int,
) -> InvariantResult:
    """A worker that has lost ownership (stale fencing token) must never
    have a commit accepted. Any accepted stale commit is a correctness
    violation regardless of how many total effects were committed."""
    return InvariantResult(
        name="stale-owner-cannot-commit",
        passed=stale_commits_accepted == 0,
        observed=stale_commits_accepted,
        limit=0,
    )
 
 
def no_lost_committed_effect(
    committed_effects: int,
) -> InvariantResult:
    """The job's effect must eventually be committed by exactly one owner.
    Zero committed effects after recovery means work was silently dropped -
    a distinct failure mode from duplicate execution."""
    return InvariantResult(
        name="no-lost-committed-effect",
        passed=committed_effects >= 1,
        observed=committed_effects,
        limit=1,
    )
 
 
def eventually_processed_after_recovery(
    processed_within_recovery_window: bool,
) -> InvariantResult:
    """After a fault is recovered from (SIGCONT, restart, redelivery),
    the job must eventually reach a terminal committed or rejected state
    within the recovery observation window, rather than hanging indefinitely."""
    return InvariantResult(
        name="eventually-processed-after-recovery",
        passed=processed_within_recovery_window,
        observed=1 if processed_within_recovery_window else 0,
        limit=1,
    )
