from services.auditor.invariant_validator import InvariantSnapshot, validate_invariants


def main() -> None:
    result = validate_invariants(
        InvariantSnapshot(
            duplicate_commits=0,
            stale_write_rejections=25,
            jobs_stuck_running=0,
            reconciled_jobs=1,
            lease_reclaims=8,
            total_runs=200,
        )
    )
    print(result)


if __name__ == "__main__":
    main()
