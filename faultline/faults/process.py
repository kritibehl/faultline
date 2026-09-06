from __future__ import annotations

from collections.abc import Callable
from subprocess import CompletedProcess

from faultline.faults.base import FaultDescription, FaultInjector


Runner = Callable[..., CompletedProcess[str]]


class DockerProcessPauseFault(FaultInjector):
    """Pause and resume a Docker container process with Unix signals."""

    name = "pause"

    def __init__(self, runner: Runner) -> None:
        self._runner = runner

    def inject(self, target: str) -> None:
        self._runner(
            "docker",
            "kill",
            "--signal=SIGSTOP",
            target,
        )

    def recover(
        self,
        target: str,
        *,
        check: bool = True,
    ) -> None:
        self._runner(
            "docker",
            "kill",
            "--signal=SIGCONT",
            target,
            check=check,
        )

    def describe(self) -> FaultDescription:
        return FaultDescription(
            name=self.name,
            inject="SIGSTOP",
            recover="SIGCONT",
        )


class DockerProcessKillFault(FaultInjector):
    """Kill a Docker container process and recover by restarting it."""

    name = "kill"

    def __init__(self, runner: Runner) -> None:
        self._runner = runner

    def inject(self, target: str) -> None:
        self._runner(
            "docker",
            "kill",
            "--signal=SIGKILL",
            target,
        )

    def recover(
        self,
        target: str,
        *,
        check: bool = True,
    ) -> None:
        self._runner(
            "docker",
            "start",
            target,
            check=check,
        )

    def describe(self) -> FaultDescription:
        return FaultDescription(
            name=self.name,
            inject="SIGKILL",
            recover="docker start",
        )
