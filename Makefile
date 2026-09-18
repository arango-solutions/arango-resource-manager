.PHONY: help install check backend frontend start backend-bg frontend-bg stop status logs kill cleanup
.DEFAULT_GOAL := help

# Where the backgrounded processes write. Both a log and a pidfile per process,
# so `stop` and `status` have something to work from across separate `make` runs.
LOGS := logs

# Self-documenting: every target with a `##` comment shows up in `make help`.
help:  ## List the targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install backend (uv) and frontend (npm) dependencies
	cd backend && uv sync
	cd frontend && npm install

check:  ## Run every gate: ruff, mypy, pytest, and the frontend typecheck
	cd backend && $(MAKE) check
	cd frontend && npm run typecheck && npm test

backend:  ## Serve the API in the foreground on http://localhost:8000
	cd backend && $(MAKE) run

frontend:  ## Serve the UI in the foreground on http://localhost:5173
	cd frontend && npm run dev

# -- backgrounded, for when you want both up and your shell back ------------

start: backend-bg frontend-bg  ## Start both in the background
	@echo "→ make logs to follow, make stop to shut down"

backend-bg:  ## Start the API in the background, logging to logs/backend.log
	@mkdir -p $(LOGS)
	@if [ -f $(LOGS)/backend.pid ] && kill -0 `cat $(LOGS)/backend.pid` 2>/dev/null; then \
		echo "backend already running (pid `cat $(LOGS)/backend.pid`)"; \
	else \
		cd backend && nohup uv run uvicorn app.main:app --reload \
			> ../$(LOGS)/backend.log 2>&1 & \
		echo $$! > $(LOGS)/backend.pid; \
		echo "backend  → http://localhost:8000/docs  ($(LOGS)/backend.log)"; \
	fi

frontend-bg:  ## Start the UI in the background, logging to logs/frontend.log
	@mkdir -p $(LOGS)
	@if [ -f $(LOGS)/frontend.pid ] && kill -0 `cat $(LOGS)/frontend.pid` 2>/dev/null; then \
		echo "frontend already running (pid `cat $(LOGS)/frontend.pid`)"; \
	else \
		cd frontend && nohup npm run dev > ../$(LOGS)/frontend.log 2>&1 & \
		echo $$! > $(LOGS)/frontend.pid; \
		echo "frontend → http://localhost:5173  ($(LOGS)/frontend.log)"; \
	fi

# The pid recorded above is the launcher (uv, npm), which is not the process
# holding the port - so kill its children too, then sweep by command line for
# anything the pidfile lost track of. Both patterns are anchored on this
# checkout, so a copy of this repo running elsewhere is left alone.
stop:  ## Stop whatever start put in the background
	@for name in backend frontend; do \
		pidfile=$(LOGS)/$$name.pid; \
		if [ -f $$pidfile ]; then \
			pid=`cat $$pidfile`; \
			pkill -P $$pid 2>/dev/null || true; \
			kill $$pid 2>/dev/null || true; \
			rm -f $$pidfile; \
			echo "stopped $$name (pid $$pid)"; \
		fi; \
	done
	@pkill -f 'uvicorn app.main:app' 2>/dev/null || true
	@pkill -f '$(CURDIR)/frontend/node_modules' 2>/dev/null || true
	@echo "→ stopped"

status:  ## Report whether the backgrounded processes are up
	@for name in backend frontend; do \
		pidfile=$(LOGS)/$$name.pid; \
		if [ -f $$pidfile ] && kill -0 `cat $$pidfile` 2>/dev/null; then \
			printf "  %-9s running (pid %s)\n" $$name `cat $$pidfile`; \
		else \
			printf "  %-9s stopped\n" $$name; \
		fi; \
	done

logs:  ## Follow both background logs
	@touch $(LOGS)/backend.log $(LOGS)/frontend.log 2>/dev/null || true
	tail -f $(LOGS)/backend.log $(LOGS)/frontend.log

# When `stop` leaves something behind - a reloader that outlived its parent, a
# run started by hand rather than by `start`. This does not wait for a clean
# shutdown, so reach for `stop` first.
kill:  ## Force-stop anything from this checkout still holding a port
	@pkill -9 -f 'uvicorn app.main:app' 2>/dev/null || true
	@pkill -9 -f '$(CURDIR)/frontend/node_modules' 2>/dev/null || true
	@rm -f $(LOGS)/backend.pid $(LOGS)/frontend.pid
	@echo "→ killed"

cleanup: kill  ## Force-stop, then delete the logs
	@rm -rf $(LOGS)
	@echo "→ removed $(LOGS)/"
