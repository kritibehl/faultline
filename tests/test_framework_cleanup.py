from faultline.adapters import celery


def test_celery_lifecycle_recovers_worker_a_best_effort(monkeypatch):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(celery, "run", fake_run)

    lifecycle = celery.build_run_lifecycle("pause")
    lifecycle.cleanup()

    assert len(calls) == 1

    args, kwargs = calls[0]

    assert args == (
        "docker",
        "kill",
        "--signal=SIGCONT",
        celery.WORKER_A,
    )

    assert kwargs["check"] is False


def test_celery_capabilities_are_conservative():
    capabilities = celery.CAPABILITIES

    assert capabilities.process_pause is True
    assert capabilities.redelivery is True
    assert capabilities.visibility_expiry is True

    assert capabilities.process_kill is False
    assert capabilities.broker_disconnect is False


def test_run_race_cleans_up_when_runner_fails(monkeypatch):
    cleanup_calls = []

    class FakeLifecycle:
        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            cleanup_calls.append(
                (exc_type, exc_value)
            )
            return False

    def fail_run(*args, **kwargs):
        raise RuntimeError("runner failed")

    monkeypatch.setattr(
        celery,
        "build_run_lifecycle",
        lambda fault: FakeLifecycle(),
    )

    monkeypatch.setattr(
        celery,
        "_run_race",
        fail_run,
    )

    try:
        celery.run_race(
            "unsafe",
            fault="pause",
        )
    except RuntimeError as exc:
        assert str(exc) == "runner failed"
    else:
        raise AssertionError("expected runner failure")

    assert len(cleanup_calls) == 1
    assert cleanup_calls[0][0] is RuntimeError
