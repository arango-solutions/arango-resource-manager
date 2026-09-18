.PHONY: help install check backend frontend start backend-bg frontend-bg stop status logs kill cleanup
.DEFAULT_GOAL := help

# Where the backgrounded processes write. A log and a pgidfile per process, so
# `stop` and `status` have something to work from across separate `make` runs.
LOGS := logs

# We record a process GROUP id, not a pid. `set -m` in the start rules makes each
# service its own group leader, and a process keeps its group even when its parent
# dies and it is reparented to init - which is exactly how a uvicorn --reload
# worker used to survive `make stop` and keep sitting on port 8000.
#
# Before signalling, confirm the group still holds a process from this checkout.
# Group ids are recycled once ours exit, and we must never signal a group we did
# not spawn. The start rules cd to an absolute path so the group leader's own
# command line carries $(CURDIR) from the very first instant.
ours = [ -f $(LOGS)/$(1).pgid ] && ps -o command= -g `cat $(LOGS)/$(1).pgid` 2>/dev/null | grep -q '$(CURDIR)'

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
	@if $(call ours,backend); then \
		echo "backend already running (pgid `cat $(LOGS)/backend.pgid`)"; \
	else \
		set -m; \
		cd $(CURDIR)/backend && nohup uv run uvicorn app.main:app --reload \
			> $(CURDIR)/$(LOGS)/backend.log 2>&1 & \
		echo $$! > $(LOGS)/backend.pgid; \
		echo "backend  → http://localhost:8000/docs  ($(LOGS)/backend.log)"; \
	fi

frontend-bg:  ## Start the UI in the background, logging to logs/frontend.log
	@mkdir -p $(LOGS)
	@if $(call ours,frontend); then \
		echo "frontend already running (pgid `cat $(LOGS)/frontend.pgid`)"; \
	else \
		set -m; \
		cd $(CURDIR)/frontend && nohup npm run dev \
			> $(CURDIR)/$(LOGS)/frontend.log 2>&1 & \
		echo $$! > $(LOGS)/frontend.pgid; \
		echo "frontend → http://localhost:5173  ($(LOGS)/frontend.log)"; \
	fi

# Signalling the negative pgid reaches every process in the group - the launcher
# (uv, npm), the reloader, and any worker orphaned along the way - and reaches
# nothing else. No command-line sweeps: a pattern broad enough to catch a stray
# worker is also broad enough to catch an unrelated `make check` sharing the venv.
stop:  ## Stop whatever start put in the background
	@for name in backend frontend; do \
		pgidfile=$(LOGS)/$$name.pgid; \
		if [ ! -f $$pgidfile ]; then \
			echo "  $$name    not running"; \
			continue; \
		fi; \
		pgid=`cat $$pgidfile`; \
		if ps -o command= -g $$pgid 2>/dev/null | grep -q '$(CURDIR)'; then \
			kill -TERM -- -$$pgid 2>/dev/null || true; \
			echo "  stopped $$name (pgid $$pgid)"; \
		else \
			echo "  $$name    pgid $$pgid is not ours, left alone"; \
		fi; \
		rm -f $$pgidfile; \
	done
	@echo "→ stopped"

# Reports on the process group, not just the pgidfile: a pgidfile can be missing
# while a process still holds the port, which is what made `status` say "stopped"
# about a backend that was very much alive.
status:  ## Report whether the backgrounded processes are up
	@for name in backend frontend; do \
		pgidfile=$(LOGS)/$$name.pgid; \
		if [ -f $$pgidfile ] && ps -o command= -g `cat $$pgidfile` 2>/dev/null | grep -q '$(CURDIR)'; then \
			printf "  %-9s running (pgid %s)\n" $$name `cat $$pgidfile`; \
		else \
			printf "  %-9s stopped\n" $$name; \
		fi; \
	done
	@for port in 8000 5173; do \
		pid=`lsof -nP -tiTCP:$$port -sTCP:LISTEN 2>/dev/null | head -1`; \
		[ -n "$$pid" ] && printf "  port %s   held by pid %s\n" $$port $$pid; \
	done; true

logs:  ## Follow both background logs
	@mkdir -p $(LOGS)
	@touch $(LOGS)/backend.log $(LOGS)/frontend.log 2>/dev/null || true
	tail -f $(LOGS)/backend.log $(LOGS)/frontend.log

# When `stop` leaves something behind. This does not wait for a clean shutdown,
# so reach for `stop` first. It still only signals groups we started; a run
# started by hand is reported rather than killed, because we cannot tell such a
# process apart from someone else's work without guessing at command lines.
kill:  ## Force-stop anything this checkout started in the background
	@for name in backend frontend; do \
		pgidfile=$(LOGS)/$$name.pgid; \
		[ -f $$pgidfile ] || continue; \
		pgid=`cat $$pgidfile`; \
		if ps -o command= -g $$pgid 2>/dev/null | grep -q '$(CURDIR)'; then \
			kill -KILL -- -$$pgid 2>/dev/null || true; \
			echo "  killed $$name (pgid $$pgid)"; \
		fi; \
		rm -f $$pgidfile; \
	done
	@for port in 8000 5173; do \
		pid=`lsof -nP -tiTCP:$$port -sTCP:LISTEN 2>/dev/null | head -1`; \
		if [ -n "$$pid" ]; then \
			echo "  ! port $$port still held by pid $$pid (not started by make; kill it yourself)"; \
			ps -o pid=,command= -p $$pid | sed 's/^/      /'; \
		fi; \
	done; true
	@echo "→ killed"

cleanup: kill  ## Force-stop, then delete the logs
	@rm -rf $(LOGS)
	@echo "→ removed $(LOGS)/"
