"""Unit tests for evidence-based repeated-trial reporting; Docker is not needed."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from faultline import trials


def create_run(tmp_path: Path, name: str, *, selected: str = "PASS",
               adapter: str = "celery", ownership: str = "PASS",
               live: dict | None = None, audit_status: str = "PASS") -> Path:
    root = tmp_path / name
    root.mkdir(parents=True)
    for filename in ("history.jsonl", "worker-a.log", "worker-b.log"):
        (root / filename).write_text("\n")
    audit = {"status": audit_status, "elapsed_seconds": 12.4}
    (root / "recovery-audit.json").write_text(json.dumps(audit))
    report = {
        "adapter": adapter,
        "mode": "fenced" if adapter == "celery" else "idempotent",
        "window": "pre-commit" if adapter == "celery" else "post-commit",
        "invariant": "no-lost-committed-effect",
        "result": selected, "committed_effects": 1,
        "recovery_audit": audit,
        "live_recovery_observation": live if live is not None else {
            "status": "OBSERVED", "clock": "monotonic", "within_deadline": True,
            "deadline_seconds": 60.0, "elapsed_seconds": 14.2,
        },
    }
    if adapter == "celery":
        report["ownership_audit"] = {"status": ownership}
    (root / "report.json").write_text(json.dumps(report))
    return root


def test_valid_celery_requires_all_evidence(tmp_path):
    folder = create_run(tmp_path, "test")
    observed = trials.classify(trials.SCENARIOS["celery-fenced"], 0, folder)
    assert observed["verdict"] == "VERIFIED_PASS"
    assert observed["live_elapsed_seconds"] == 14.2
    assert observed["offline_elapsed_seconds"] == 12.4


def test_valid_bullmq_without_fencing_audit(tmp_path):
    folder = create_run(tmp_path, "test", adapter="bullmq")
    observed = trials.classify(trials.SCENARIOS["bullmq-idempotent"], 0, folder)
    assert observed["verdict"] == "VERIFIED_PASS"
    assert observed["ownership_audit"] is None


def test_missing_report_is_inconclusive(tmp_path):
    observed = trials.classify(trials.SCENARIOS["celery-fenced"], 2, tmp_path)
    assert observed["verdict"] == "INCONCLUSIVE"


def test_failure_artifact_is_inconclusive_even_with_stale_pass_report(tmp_path):
    folder = create_run(tmp_path, "test")
    (folder / "run-failure.json").write_text(json.dumps({"failure_kind": "OBSERVATION_TIMEOUT"}))
    observed = trials.classify(trials.SCENARIOS["celery-fenced"], 0, folder)
    assert observed["verdict"] == "INCONCLUSIVE"


def test_missing_log_is_inconclusive(tmp_path):
    folder = create_run(tmp_path, "test")
    (folder / "worker-b.log").unlink()
    assert trials.classify(trials.SCENARIOS["celery-fenced"], 0, folder)["verdict"] == "INCONCLUSIVE"


def test_bad_ownership_cannot_be_pass(tmp_path):
    folder = create_run(tmp_path, "test", ownership="FAIL")
    assert trials.classify(trials.SCENARIOS["celery-fenced"], 0, folder)["verdict"] == "INCONCLUSIVE"


def test_bad_ownership_only_missing(tmp_path):
    folder = create_run(tmp_path, "test", ownership="INCONCLUSIVE")
    assert trials.classify(trials.SCENARIOS["celery-fenced"], 0, folder)["verdict"] == "INCONCLUSIVE"


def test_offline_audit_not_pass_is_inconclusive(tmp_path):
    folder = create_run(tmp_path, "test", audit_status="INCONCLUSIVE")
    assert trials.classify(trials.SCENARIOS["celery-fenced"], 0, folder)["verdict"] == "INCONCLUSIVE"


def test_live_elapsed_over_budget_inconclusive(tmp_path):
    folder = create_run(tmp_path, "test", live={
        "status": "OBSERVED", "clock": "monotonic", "within_deadline": True,
        "deadline_seconds": 60, "elapsed_seconds": 61,
    })
    assert trials.classify(trials.SCENARIOS["celery-fenced"], 0, folder)["verdict"] == "INCONCLUSIVE"


def test_runner_nonzero_cannot_be_pass(tmp_path):
    folder = create_run(tmp_path, "test")
    assert trials.classify(trials.SCENARIOS["celery-fenced"], 2, folder)["verdict"] == "INCONCLUSIVE"


def test_wrong_adapter_is_inconclusive(tmp_path):
    folder = create_run(tmp_path, "test", adapter="bullmq")
    assert trials.classify(trials.SCENARIOS["celery-fenced"], 0, folder)["verdict"] == "INCONCLUSIVE"


def test_detected_failure_control(tmp_path):
    folder = create_run(tmp_path, "test", selected="FAIL")
    report = json.loads((folder / "report.json").read_text())
    report["mode"] = "unsafe"
    report["invariant"] = "at-most-one-effect"
    report["committed_effects"] = 2
    report["ownership_audit"] = {"status": "FAIL"}
    (folder / "report.json").write_text(json.dumps(report))
    result = trials.classify(trials.SCENARIOS["celery-unsafe-control"], 1, folder)
    assert result["verdict"] == "DETECTED_FAIL"


def test_report_and_durable_audit_mismatch(tmp_path):
    folder = create_run(tmp_path, "test")
    (folder / "recovery-audit.json").write_text(json.dumps({"status": "PASS", "elapsed_seconds": 7}))
    assert trials.classify(trials.SCENARIOS["celery-fenced"], 0, folder)["verdict"] == "INCONCLUSIVE"


def test_percentile_nearest_rank():
    assert trials.percentile([], 0.95) is None
    assert trials.percentile([9.0, 1.0, 3.0, 4.0], 0.95) == 9.0
    assert trials.percentile([9.0, 1.0, 3.0, 4.0], 0.5) == 3.0


def test_percentile_invalid_latency():
    with pytest.raises(ValueError):
        trials.percentile([-1, 2], 0.95)


def test_stats_do_not_hide_inconclusive_and_failures():
    rows = [
        {"case": "safe", "trial": 1, "expected": "PASS", "verdict": "VERIFIED_PASS", "live_elapsed_seconds": 2.0},
        {"case": "safe", "trial": 2, "expected": "PASS", "verdict": "INCONCLUSIVE", "live_elapsed_seconds": None},
        {"case": "unsafe", "trial": 1, "expected": "FAIL", "verdict": "DETECTED_FAIL", "live_elapsed_seconds": None},
    ]
    summary = trials.summarize(rows)
    assert summary["attempted"] == 3
    assert summary["verified_pass"] == 1
    assert summary["detected_fail"] == 1
    assert summary["inconclusive"] == 1
    assert summary["expected_outcomes"] == 2
    assert summary["observed_expected_outcome_rate"] == 0.6667
    assert summary["verified_live_latency_p95_seconds"] == 2.0
    assert summary["by_case"]["safe"]["attempted"] == 2
    assert summary["by_case"]["unsafe"]["verified_live_latency_p95_seconds"] is None


def test_no_samples_never_claims_zero_latency():
    summary = trials.summarize([])
    assert summary["verified_live_latency_p50_seconds"] is None
    assert summary["observed_expected_outcome_rate"] is None


def test_discovery_requires_unique_new_matching_dir(tmp_path):
    before = set()
    a = tmp_path / "20261016T100000Z-celery-pre-commit-fenced-aaaa1111"
    a.mkdir()
    assert trials.discover_new_run(tmp_path, trials.SCENARIOS["celery-fenced"], before) == a
    before.add(a)
    assert trials.discover_new_run(tmp_path, trials.SCENARIOS["celery-fenced"], before) is None
    b = tmp_path / "20261016T100001Z-celery-pre-commit-fenced-bbbb2222"
    b.mkdir()
    assert trials.discover_new_run(tmp_path, trials.SCENARIOS["celery-fenced"], set()) is None


def test_dry_run_is_read_only(tmp_path, monkeypatch, capsys):
    (tmp_path / "pyproject.toml").write_text("[build-system]\nrequires=[]\n")
    (tmp_path / "faultline").mkdir()
    monkeypatch.chdir(tmp_path)
    assert trials.main(["--cases", "celery-fenced,bullmq-idempotent", "--trials", "2", "--dry-run"]) == 0
    assert "DRY RUN" in capsys.readouterr().out
    assert not (tmp_path / "artifacts").exists()


def test_invalid_cases_fail_without_docker(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[build-system]\nrequires=[]\n")
    (tmp_path / "faultline").mkdir()
    monkeypatch.chdir(tmp_path)
    assert trials.main(["--cases", "unknown", "--dry-run"]) == 2


def test_batch_execution_collects_real_report_contract_without_docker(tmp_path, monkeypatch):
    import argparse
    import subprocess

    (tmp_path / "pyproject.toml").write_text("[build-system]\nrequires=[]\n")
    (tmp_path / "faultline").mkdir()
    monkeypatch.chdir(tmp_path)

    def simulated_cli(argv, **kwargs):
        assert argv[:2] == ["faultline", "test"]
        run = create_run(
            tmp_path / "artifacts" / "runs",
            "20261016T200000Z-celery-pre-commit-fenced-abcdef01",
        )
        assert run.is_dir()
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(trials.subprocess, "run", simulated_cli)
    args = argparse.Namespace(cases="celery-fenced", trials=1, min_free_gib=0,
                              run_timeout_seconds=900, cleanup_passing=False, dry_run=False)
    assert trials.execute(args) == 0
    manifest, = (tmp_path / "artifacts" / "benchmarks").glob("*/manifest.json")
    batch = json.loads(manifest.read_text())
    assert len(batch["rows"]) == 1
    assert batch["rows"][0]["verdict"] == "VERIFIED_PASS"
    summary = json.loads((manifest.parent / "summary.json").read_text())
    assert summary["attempted"] == 1
    assert summary["completed_all_planned"]
    assert summary["by_case"]["celery-fenced"]["verified_pass"] == 1


def test_failed_batch_trial_is_not_hidden_or_cleanup_candidate(tmp_path, monkeypatch):
    import argparse
    import subprocess

    (tmp_path / "pyproject.toml").write_text("[build-system]\nrequires=[]\n")
    (tmp_path / "faultline").mkdir()
    monkeypatch.chdir(tmp_path)
    called = []

    def simulated_cli(argv, **kwargs):
        called.append(argv)
        run = tmp_path / "artifacts" / "runs" / "20261016T200000Z-celery-pre-commit-fenced-abcdef01"
        run.mkdir(parents=True)
        (run / "run-failure.json").write_text(json.dumps({"failure_kind": "OBSERVATION_TIMEOUT"}))
        return subprocess.CompletedProcess(argv, 2)

    monkeypatch.setattr(trials.subprocess, "run", simulated_cli)
    args = argparse.Namespace(cases="celery-fenced", trials=1, min_free_gib=0,
                              run_timeout_seconds=900, cleanup_passing=True, dry_run=False)
    assert trials.execute(args) == 1
    assert len(called) == 1  # No attempt to clean failed experiment
    summary, = (tmp_path / "artifacts" / "benchmarks").glob("*/summary.json")
    data = json.loads(summary.read_text())
    assert data["inconclusive"] == 1
    assert data["verified_pass"] == 0
