from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType


class RunLifecycle(ABC):
    """Resources and recovery actions owned by one framework run."""

    def __enter__(self) -> "RunLifecycle":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        self.cleanup()
        return False

    @abstractmethod
    def cleanup(self) -> None:
        """Best-effort cleanup performed when a run exits."""
        raise NotImplementedError
