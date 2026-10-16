from pathlib import Path
from types import SimpleNamespace

import pytest

import faultline.cli as cli
from faultline.adapters import registry
from faultline.adapters.base import RunError


@pytest.mark.parametrize("adapter", ["celery", "bullmq"])
@pytest.mark.parametrize(
    "invariant",
    ["at-most-one-effect", "no-lost-committed-effect"],
)
def test_cli_forwards_selected_invariant(
    monkeypatch, adapter, invariant
):
    observed = {}

    def fake_run(adapter_name, mode, *, fault, window, invariant):
        observed.update(
            adapter=adapter_name,
            mode=mode,
            fault=fault,
            window=window,
            invariant=invariant,
        )
        return {"result": "PASS"}, Path("unused")

    monkeypatch.setattr(cli, "run_race", fake_run)

    args = cli.build_parser().parse_args(
        [
            "test",
            "--adapter", adapter,
            "--implementation", "fenced",
            "--invariant", invariant,
        ]
    )

    assert cli.run_test(args) == 0
    assert observed["adapter"] == adapter
    assert observed["mode"] == "fenced"
    assert observed["invariant"] == invariant


@pytest.mark.parametrize(
    "adapter", ["celery", "bullmq"]
)
def test_registry_forwards_invariant(monkeypatch, adapter):
    observed = {}

    def fake_run(mode, *, fault, window, invariant):
        observed["invariant"] = invariant
        return {"result": "PASS"}, Path("unused")

    monkeypatch.setitem(
        registry.ADAPTERS,
        adapter,
        SimpleNamespace(run_race=fake_run),
    )

    report, _ = registry.run_race(
        adapter,
        "fenced",
        fault="pause",
        window="pre-commit",
        invariant="no-lost-committed-effect",
    )

    assert report["result"] == "PASS"
    assert observed["invariant"] == "no-lost-committed-effect"


def test_compare_rejects_unsupported_invariant():
    args = cli.build_parser().parse_args(
        [
            "compare",
            "--adapter", "celery",
            "--invariant", "no-lost-committed-effect",
        ]
    )

    with pytest.raises(RunError, match="compare currently"):
        cli.run_compare(args)
