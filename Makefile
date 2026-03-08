DATABASE_URL ?= postgresql://faultline:faultline@localhost:5432/faultline

# ─────────────────────────────────────────────────────────
# Core
# ─────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "  Faultline — available targets"
	@echo ""
	@echo "  Core:"
	@echo "    make up            Start docker services"
	@echo "    make down          Stop docker services"
	@echo "    make restart       Restart docker services"
	@echo "    make logs          Follow docker logs"
	@echo "    make migrate       Run DB migrations"
	@echo "    make test          Run full pytest suite"
	@echo "    make clean         Remove __pycache__ files"
	@echo ""
	@echo "  Failure Drills:"
	@echo "    make drill-01      Worker crash + lease recovery"
	@echo "    make drill-02      Duplicate submission (idempotency)"
	@echo "    make drill-03      DB outage + recovery"
	@echo "    make drill-all     Run all drills"
	@echo ""
	@echo "  Failure Validation:"
	@echo "    make lease-race          Single lease-expiry race run"
	@echo "    make lease-race-500      500-run deterministic harness"
	@echo "    make lease-race-log      Race run with structured log output"
	@echo "    make autopsy-lease-race  Race run + write autopsy log"
	@echo ""

up:
	docker compose up -d

down:
	docker compose down

restart: down up

logs:
	docker compose logs -f

migrate:
	DATABASE_URL=$(DATABASE_URL) python3 services/api/migrate.py

test:
	DATABASE_URL=$(DATABASE_URL) pytest tests/ -v

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +

# ─────────────────────────────────────────────────────────
# Failure Drills
# ─────────────────────────────────────────────────────────

drill-01:
	@echo "Running Drill 01: Worker crash mid-execution..."
	@docker compose stop worker 2>/dev/null || true
	@DATABASE_URL=$(DATABASE_URL) PYTHONPATH=$(shell pwd) bash drills/run_all.sh 2>&1 | grep -A 20 "Drill 01"
	@docker compose up -d worker

drill-02:
	@echo "Running Drill 02: Duplicate submission..."
	@DATABASE_URL=$(DATABASE_URL) bash -c '\
		source .venv/bin/activate 2>/dev/null || true; \
		python3 -c " \
import psycopg2; \
conn = psycopg2.connect(\"$(DATABASE_URL)\"); \
cur = conn.cursor(); \
cur.execute(\"DELETE FROM jobs WHERE idempotency_key=\047drill-02-payment\047\"); \
conn.commit()"; \
		curl -s -X POST http://localhost:8000/jobs \
			-H "Content-Type: application/json" \
			-d '"'"'{"payload":{"task":"payment"},"idempotency_key":"drill-02-payment"}'"'"' | python3 -m json.tool; \
		curl -s -X POST http://localhost:8000/jobs \
			-H "Content-Type: application/json" \
			-d '"'"'{"payload":{"task":"payment"},"idempotency_key":"drill-02-payment"}'"'"' | python3 -m json.tool'

drill-03:
	@echo "Running Drill 03: DB outage recovery..."
	@docker compose pause postgres
	@echo "Postgres paused. Waiting 35s for lease to expire..."
	@sleep 35
	@docker compose unpause postgres
	@echo "Postgres restored."

drill-all:
	@echo "Running all failure drills..."
	@docker compose stop worker 2>/dev/null || true
	@DATABASE_URL=$(DATABASE_URL) PYTHONPATH=$(shell pwd) bash drills/run_all.sh
	@docker compose up -d worker

# ─────────────────────────────────────────────────────────
# Lease Race Validation
# ─────────────────────────────────────────────────────────

lease-race:
	@docker compose stop worker 2>/dev/null || true
	@RACE_RUNS=1 DATABASE_URL=$(DATABASE_URL) pytest -q -s \
		tests/test_lease_race_fencing.py::test_lease_expiry_race_is_blocked_by_fencing
	@docker compose up -d worker

lease-race-500:
	@echo "Running 500-run deterministic race harness..."
	@echo "This will take ~22 minutes."
	@docker compose stop worker 2>/dev/null || true
	@mkdir -p tests/results docs/autopsy/assets
	@RACE_RUNS=500 DATABASE_URL=$(DATABASE_URL) pytest -q -s \
		tests/test_lease_race_fencing.py::test_lease_expiry_race_is_blocked_by_fencing
	@echo "Results written to tests/results/lease_race_500_runs.txt"
	@docker compose up -d worker

lease-race-log:
	@docker compose stop worker 2>/dev/null || true
	@mkdir -p docs/autopsy/assets
	@rm -f docs/autopsy/assets/logs.jsonl
	@RACE_RUNS=1 DATABASE_URL=$(DATABASE_URL) \
		AUTOPSY_LOG_PATH=docs/autopsy/assets/logs.jsonl \
		pytest -q -s tests/test_lease_race_fencing.py::test_lease_expiry_race_is_blocked_by_fencing \
		| tee /tmp/lease_race.log
	@echo ""
	@echo "---- extracted events ----"
	@grep -E '"event"' docs/autopsy/assets/logs.jsonl | head -n 25 || true
	@docker compose up -d worker

autopsy-lease-race:
	@docker compose stop worker 2>/dev/null || true
	@mkdir -p docs/autopsy/assets
	@rm -f docs/autopsy/assets/logs.jsonl
	@RACE_RUNS=1 DATABASE_URL=$(DATABASE_URL) \
		AUTOPSY_LOG_PATH=docs/autopsy/assets/logs.jsonl \
		pytest -q -s tests/test_lease_race_fencing.py::test_lease_expiry_race_is_blocked_by_fencing
	@echo "Wrote docs/autopsy/assets/logs.jsonl"
	@docker compose up -d worker

.PHONY: help up down restart logs migrate test clean \
        drill-01 drill-02 drill-03 drill-all \
        lease-race lease-race-500 lease-race-log autopsy-lease-race