from __future__ import annotations

from pathlib import Path

from faultline.adapters import (
    bullmq,
    celery,
)
from faultline.adapters.base import RunError


ADAPTERS = {
    "celery": celery,
    "bullmq": bullmq,
}

ADAPTER_NAMES = tuple(ADAPTERS)


def run_race(
    adapter: str,
    mode: str,
    *,
    fault: str,
    window: str,
) -> tuple[dict[str, object], Path]:
    module = ADAPTERS.get(adapter)

    if module is None:
        raise RunError(
            f"unknown adapter={adapter!r}"
        )

    return module.run_race(
        mode,
        fault=fault,
        window=window,
    )
