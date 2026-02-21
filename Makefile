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