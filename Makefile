.PHONY: install lint typecheck test eval api worker migrate seed

install:
	python -m pip install -e ".[dev]"

lint:
	ruff check .
	ruff format --check .

typecheck:
	mypy app evals

test:
	pytest

eval:
	python -m evals.runner

api:
	uvicorn app.main:app --reload

worker:
	arq app.scheduler.worker.WorkerSettings

migrate:
	alembic upgrade head

seed:
	python -m scripts.seed_family

