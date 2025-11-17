.PHONY: up migrate dev

up:
	docker compose up --build

migrate:
	docker compose run --rm bot alembic upgrade head

dev:
	PYTHONPATH=. python3.11 -m uvicorn apps.bot.main:app --reload --host 0.0.0.0 --port 8000
