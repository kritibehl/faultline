"""Live shared deadline for *observation* of Worker B's terminal event.

Starts after successful fault injection; stops after Worker B's terminal marker
is observed. Uses a monotonic clock, bounds sleeps and Python-owned Docker
subprocesses, and does not purport to enforce broker ACK, full job completion,
or a total experiment/setup deadline. Timeout => observation inconclusive.
"""
from __future__ import annotations

import contextvars
import math
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from faultline.adapters.base import RunError


class RecoveryDeadlineExceeded(RunError, TimeoutError):
    """An observation deadline expired; not proof of a liveness violation."""


@dataclass
class RecoveryObservation:
    budget_seconds: float
    started: float
    stop: float | None = None

    def remaining(self, operation: str = "recovery observation") -> float:
        value = self.budget_seconds - (time.monotonic() - self.started)
        if value <= 0:
            raise RecoveryDeadlineExceeded(
                f"recovery observation deadline exceeded "
                f"({self.budget_seconds:g}s) during {operation}"
            )
        return value

    def elapsed(self) -> float:
        end = self.stop if self.stop is not None else time.monotonic()
        return max(0.0, end - self.started)

    def as_report(self) -> dict[str, object]:
        if self.stop is None:
            raise ValueError("cannot report an incomplete observation")
        return {
            "status": "OBSERVED",
            "clock": "monotonic",
            "scope": "fault injection to worker-B terminal marker observation",
            "deadline_seconds": self.budget_seconds,
            "elapsed_seconds": round(self.elapsed(), 3),
            "within_deadline": self.elapsed() <= self.budget_seconds,
            "limitation": (
                "bounds Python polling, sleeps and Docker subprocesses in "
                "this observation stage; not full experiment or broker ACK"
            ),
        }


_ACTIVE: contextvars.ContextVar[RecoveryObservation | None] = (
    contextvars.ContextVar("faultline_recovery_observation", default=None)
)


def current_observation() -> RecoveryObservation | None:
    return _ACTIVE.get()


@contextmanager
def recovery_observation_deadline(
    seconds: float = 60,
) -> Iterator[RecoveryObservation]:
    if (not isinstance(seconds, (int, float)) or isinstance(seconds, bool)
            or not math.isfinite(seconds) or seconds <= 0):
        raise ValueError("recovery deadline must be finite and positive")
    if current_observation() is not None:
        raise RuntimeError("nested recovery observation deadlines are unsupported")

    observation = RecoveryObservation(float(seconds), time.monotonic())
    token = _ACTIVE.set(observation)
    try:
        yield observation
        observation.remaining("terminal observation completion")
        observation.stop = time.monotonic()
        if observation.elapsed() > observation.budget_seconds:
            observation.remaining("terminal observation completion")
    finally:
        _ACTIVE.reset(token)


def bounded_sleep(seconds: float) -> None:
    observation = current_observation()
    if observation is None:
        time.sleep(seconds)
        return
    remaining = observation.remaining("sleep")
    time.sleep(min(seconds, remaining))
    observation.remaining("sleep")


def bounded_subprocess_run(*args, **kwargs):
    """Apply the *same* budget to each subprocess in the active stage."""
    observation = current_observation()
    if observation is None:
        return subprocess.run(*args, **kwargs)

    remaining = observation.remaining("Docker subprocess")
    existing = kwargs.get("timeout")
    if existing is not None:
        remaining = min(remaining, existing)
    kwargs["timeout"] = remaining
    try:
        result = subprocess.run(*args, **kwargs)
    except subprocess.TimeoutExpired as exc:
        raise RecoveryDeadlineExceeded(
            "recovery observation deadline exceeded or Docker subprocess "
            f"timed out during {str(args[0])[:180]}"
        ) from exc
    observation.remaining("Docker subprocess completion")
    return result
