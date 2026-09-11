.PHONY: install check backend frontend

install:
	cd backend && uv sync
	cd frontend && npm install

check:
	cd backend && $(MAKE) check
	cd frontend && npm run typecheck

backend:
	cd backend && $(MAKE) run

frontend:
	cd frontend && npm run dev
