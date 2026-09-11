.PHONY: install lint typecheck test smoke check run probe

install:
	uv sync

lint:
	uv run ruff check app tests scripts
	uv run ruff format --check app tests scripts

format:
	uv run ruff format app tests scripts

typecheck:
	uv run mypy app

test:
	uv run pytest

# The assembled app, served from fixtures: boots, routes answer, data is real.
smoke:
	uv run pytest tests/test_smoke.py -q

check: lint typecheck test smoke

run:
	uv run uvicorn app.main:app --reload

probe:
	uv run python scripts/probe_cluster.py

probe-dump:
	uv run python scripts/probe_cluster.py --dump
