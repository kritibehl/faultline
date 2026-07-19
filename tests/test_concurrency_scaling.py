from pathlib import Path

from concurrency_lab.run_concurrency_scaling import build_report


def test_worker_profiles_cover_1_to_16_workers():
    report = build_report()
    workers = [row["workers"] for row in report["profiles"]]

    assert workers == [1, 2, 4, 8, 16]


def test_duplicate_commits_remain_zero_under_concurrency():
    report = build_report()

    assert report["summary"]["duplicate_commits"] == 0
    assert all(row["duplicate_commits"] == 0 for row in report["profiles"])


def test_contention_and_pool_pressure_increase_with_scale():
    report = build_report()
    profiles = {row["workers"]: row for row in report["profiles"]}

    assert profiles[16]["lease_contention_events"] > profiles[8]["lease_contention_events"]
    assert profiles[16]["retry_amplification"] > profiles[8]["retry_amplification"]
    assert profiles[16]["connection_pool_utilization_percent"] == 96
    assert profiles[16]["recovery_latency_p95_ms"] > profiles[8]["recovery_latency_p95_ms"]


def test_report_and_chart_exist():
    assert Path("reports/concurrency_scaling_report.md").exists()
    assert Path("reports/concurrency_throughput_curve.png").exists()
