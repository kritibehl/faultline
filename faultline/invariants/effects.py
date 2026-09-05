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
