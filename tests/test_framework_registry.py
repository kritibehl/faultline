from faultline.adapters import registry


def test_registry_exposes_celery_and_bullmq():
    assert set(registry.ADAPTER_NAMES) == {
        "celery",
        "bullmq",
    }


def test_registry_dispatches_to_selected_adapter(
    monkeypatch,
):
    calls = []

    def fake_run_race(
        mode,
        fault,
        window,
    ):
        calls.append(
            (mode, fault, window)
        )

        return (
            {"result": "PASS"},
            None,
        )

    monkeypatch.setattr(
        registry.bullmq,
        "run_race",
        fake_run_race,
    )

    report, _ = registry.run_race(
        "bullmq",
        "unsafe",
        fault="kill",
        window="post-commit",
    )

    assert report["result"] == "PASS"

    assert calls == [
        (
            "unsafe",
            "kill",
            "post-commit",
        )
    ]
