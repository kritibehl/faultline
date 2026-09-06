from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class FaultDescription:
    """Machine-readable description of a fault mechanism."""

    name: str
    inject: str
    recover: str

    def as_report(self) -> dict[str, str]:
        return {
            "inject": self.inject,
            "recover": self.recover,
        }


class FaultInjector(ABC):
    """Mechanism for injecting and recovering one failure type."""

    name: str

    @abstractmethod
    def inject(self, target: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def recover(
        self,
        target: str,
        *,
        check: bool = True,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def describe(self) -> FaultDescription:
        raise NotImplementedError
