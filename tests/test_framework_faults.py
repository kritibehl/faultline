from faultline.faults.process import (
    DockerProcessKillFault,
    DockerProcessPauseFault,
)


def test_pause_fault_injects_sigstop():
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))

    fault = DockerProcessPauseFault(fake_run)

    fault.inject("worker-a")

    assert calls == [
        (
            (
                "docker",
                "kill",
                "--signal=SIGSTOP",
                "worker-a",
            ),
            {},
        )
    ]


def test_pause_fault_recovers_with_sigcont():
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))

    fault = DockerProcessPauseFault(fake_run)

    fault.recover(
        "worker-a",
        check=False,
    )

    assert calls == [
        (
            (
                "docker",
                "kill",
                "--signal=SIGCONT",
                "worker-a",
            ),
            {"check": False},
        )
    ]


def test_pause_fault_description_is_machine_readable():
    def fake_run(*args, **kwargs):
        raise AssertionError("runner should not be called")

    fault = DockerProcessPauseFault(fake_run)
    description = fault.describe()

    assert description.name == "pause"
    assert description.inject == "SIGSTOP"
    assert description.recover == "SIGCONT"

    assert description.as_report() == {
        "inject": "SIGSTOP",
        "recover": "SIGCONT",
    }


def test_kill_fault_injects_sigkill():
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))

    fault = DockerProcessKillFault(fake_run)

    fault.inject("worker-a")

    assert calls == [
        (
            (
                "docker",
                "kill",
                "--signal=SIGKILL",
                "worker-a",
            ),
            {},
        )
    ]


def test_kill_fault_recovers_with_docker_start():
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))

    fault = DockerProcessKillFault(fake_run)

    fault.recover(
        "worker-a",
        check=False,
    )

    assert calls == [
        (
            (
                "docker",
                "start",
                "worker-a",
            ),
            {"check": False},
        )
    ]


def test_kill_fault_description_is_machine_readable():
    def fake_run(*args, **kwargs):
        raise AssertionError("runner should not be called")

    fault = DockerProcessKillFault(fake_run)
    description = fault.describe()

    assert description.name == "kill"
    assert description.inject == "SIGKILL"
    assert description.recover == "docker start"

    assert description.as_report() == {
        "inject": "SIGKILL",
        "recover": "docker start",
    }
