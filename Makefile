# Common tasks. Run `make` with no target to see this list.
DATE ?= $(shell date -v-1d +%F 2>/dev/null || date -d yesterday +%F)
PY   := .venv/bin/python

.PHONY: help venv run backfill test clean

help:
	@echo "make venv                       create .venv and install requirements"
	@echo "make run [DATE=YYYY-MM-DD]      run all six steps for one day (default: yesterday)"
	@echo "make backfill START=… END=…     run a date range"
	@echo "make test                       run the test suite"
	@echo "make clean                      remove db, raw files, caches"

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
