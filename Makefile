.PHONY: up down logs ps clean

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

clean:
	docker compose down -v
migrate:
	docker compose run --rm api python migrate.py
