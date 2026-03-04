.PHONY: lease-race-log
lease-race-log:
	@set -e; \
	docker compose up -d; \
	echo "Waiting for services..."; \
	sleep 2; \
	DATABASE_URL="postgresql://faultline:faultline@localhost:5432/faultline" \
	pytest -q -s tests/test_lease_race_fencing.py::test_lease_expiry_race_is_blocked_by_fencing \
	| tee /tmp/lease_race.log; \
	echo "---- extracted events ----"; \
	grep -E '"event":"(lease_acquired|execution_started|stale_write_blocked|execution_succeeded|job_succeeded)"' /tmp/lease_race.log \
	| head -n 25 || true; \
	docker compose down
# Default DATABASE_URL (used for local pytest + migrate)
DATABASE_URL ?= postgresql://faultline:faultline@localhost:5432/faultline

help:
	@echo "Available targets:"
	@echo "  make up         - Start docker services"
	@echo "  make down       - Stop docker services"
	@echo "  make restart    - Restart docker services"
	@echo "  make logs       - Follow docker logs"
	@echo "  make migrate    - Run DB migrations locally"
	@echo "  make test       - Run pytest suite"
	@echo "  make clean      - Remove __pycache__ files"

up:
	docker compose up -d

down:
	docker compose down

restart: down up

logs:
	docker compose logs -f

migrate:
	DATABASE_URL=$(DATABASE_URL) python services/api/migrate.py

test:
	DATABASE_URL=$(DATABASE_URL) pytest -q

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +

.PHONY: autopsy-lease-race repro-lease-race lease-race-500

# ============================================
# Autopsy / Failure Lab Targets
# ============================================

autopsy-lease-race:
	@set -e; \
	docker compose up -d; \
	echo "Waiting for services..."; \
	sleep 2; \
	mkdir -p docs/autopsy/assets; \
	rm -f docs/autopsy/assets/logs.jsonl; \
	DATABASE_URL="postgresql://faultline:faultline@localhost:5432/faultline" \
	AUTOPSY_LOG_PATH="docs/autopsy/assets/logs.jsonl" \
	pytest -q -s tests/test_lease_race_fencing.py::test_lease_expiry_race_is_blocked_by_fencing; \
	echo "Wrote docs/autopsy/assets/logs.jsonl"; \
	docker compose down

repro-lease-race: autopsy-lease-race
	@echo "==== TIMELINE ===="; \
	if [ -f docs/autopsy/assets/timeline.txt ]; then cat docs/autopsy/assets/timeline.txt; else echo "(missing docs/autopsy/assets/timeline.txt)"; fi; \
	echo ""; \
	echo "==== LOG EXCERPT (last 30 lines) ===="; \
	tail -n 30 docs/autopsy/assets/logs.jsonl || true

lease-race-500:
	@set -e; \
	docker compose up -d; \
	echo "Waiting for services..."; \
	sleep 2; \
	mkdir -p docs/autopsy; \
	rm -f docs/autopsy/results.txt; \
	for i in $$(seq 1 500); do \
	  echo "RUN $$i" >> docs/autopsy/results.txt; \
	  DATABASE_URL="postgresql://faultline:faultline@localhost:5432/faultline" \
	  AUTOPSY_LOG_PATH="/dev/null" \
	  pytest -q -s tests/test_lease_race_fencing.py::test_lease_expiry_race_is_blocked_by_fencing >> docs/autopsy/results.txt || exit 1; \
	done; \
	echo "500 runs complete → docs/autopsy/results.txt"; \
	docker compose down
