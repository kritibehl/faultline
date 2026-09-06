from faultline.adapters import celery


def test_best_effort_recovery_uses_sigcont(monkeypatch):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(celery, "run", fake_run)

    celery.best_effort_recover_worker_a()

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
