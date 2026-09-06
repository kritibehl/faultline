from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class RunError(RuntimeError):
    """Adapter/runtime failure distinct from an invariant violation."""

    pass


@dataclass(frozen=True)
class AdapterCapabilities:
    process_pause: bool = False
    process_kill: bool = False
    broker_disconnect: bool = False
    redelivery: bool = False
    visibility_expiry: bool = False


class WorkerAdapter(ABC):
    """Contract implemented by queue/worker integrations."""

    name: str
    capabilities: AdapterCapabilities

    @abstractmethod
    def run(
        self,
        *,
        mode: str,
        invariant: str,
    ) -> tuple[dict[str, Any], Path]:
        raise NotImplementedError
