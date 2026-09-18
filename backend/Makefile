.PHONY: help install lint format typecheck test smoke integration check run probe probe-dump
.DEFAULT_GOAL := help

# Self-documenting: every target with a `##` comment shows up in `make help`.
help:  ## List the targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:  ## Sync the virtualenv from uv.lock
	uv sync

lint:  ## Check style and formatting with ruff
	uv run ruff check app tests scripts
	uv run ruff format --check app tests scripts

format:  ## Rewrite the source in ruff's format
	uv run ruff format app tests scripts

typecheck:  ## Typecheck the app with mypy
	uv run mypy app

test:  ## Run the test suite (fixtures only, no cluster needed)
	uv run pytest

# The assembled app, served from fixtures: boots, routes answer, data is real.
smoke:  ## Boot the assembled app against fixtures and check the routes answer
	uv run pytest tests/test_smoke.py -q

integration:  ## HTTP integration tests against fixture replay
	uv run pytest -m integration -q

check: lint typecheck test smoke  ## Run lint, typecheck, test and smoke

run:  ## Serve the API with reload on http://localhost:8000
	uv run uvicorn app.main:app --reload

probe:  ## Read-only probe of the configured cluster
	uv run python scripts/probe_cluster.py

probe-dump:  ## Probe the cluster and record the response as test fixtures
	uv run python scripts/probe_cluster.py --dump
