# Common tasks. Run `make` with no target to see this list.
DATE ?= $(shell date -v-1d +%F 2>/dev/null || date -d yesterday +%F)
PY   := .venv/bin/python

DB   ?= sqlite
export SF911_DB := $(DB)

.PHONY: help venv run backfill test test-all clean db-up db-down db-shell

help:
	@echo "make venv                       create .venv and install requirements"
	@echo "make run [DATE=YYYY-MM-DD]      run all six steps for one day (default: yesterday)"
	@echo "make backfill START=… END=…     run a date range"
	@echo "make test                       run the test suite (add DB=postgres to test against Postgres)"
	@echo "make test-all                   run tests on SQLite and Postgres"
	@echo "make db-up / db-down            start / stop the Postgres container (docker compose)"
	@echo "make db-shell                   psql into the container"
	@echo "make clean                      remove db, raw files, caches"
	@echo ""
	@echo "Any target accepts DB=postgres, e.g.  make run DATE=2026-09-01 DB=postgres"

db-up:
	docker compose up -d db && docker compose exec db sh -c 'until pg_isready -U sf911 >/dev/null 2>&1; do sleep 1; done' && echo "postgres ready on :5432"

db-down:
	docker compose down

db-shell:
	docker compose exec db psql -U sf911 -d sf911

test-all:
	SF911_DB=sqlite   $(PY) -m pytest -q
	SF911_DB=postgres $(PY) -m pytest -q

venv:
	python3 -m venv .venv && $(PY) -m pip install -q -r requirements.txt

run:
	$(PY) run_pipeline.py --date $(DATE)

backfill:
	$(PY) run_pipeline.py --start $(START) --end $(END)

test:
	$(PY) -m pytest -q

clean:
	rm -rf sf911.db data/raw/*.json __pycache__ src/__pycache__ tests/__pycache__ .pytest_cache
