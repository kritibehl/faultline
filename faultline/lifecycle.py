from __future__ import annotations

import sys

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
        try:
            self.cleanup()
        except Exception as cleanup_error:
            if exc_value is None:
                raise
            print(
                f"FAULTLINE WARNING: recovery cleanup failed while handling "
                f"{type(exc_value).__name__}: {cleanup_error}",
                file=sys.stderr,
            )
        return False

    @abstractmethod
    def cleanup(self) -> None:
        """Best-effort cleanup performed when a run exits."""
        raise NotImplementedError
