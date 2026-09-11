.PHONY: install lint typecheck test check run probe

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

check: lint typecheck test

run:
	uv run uvicorn app.main:app --reload

probe:
	uv run python scripts/probe_cluster.py

probe-dump:
	uv run python scripts/probe_cluster.py --dump
