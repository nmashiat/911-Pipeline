# sf911-pipeline

Quality-gated data pipeline over San Francisco Fire/EMS 911 calls for service.

**Status:** Step 1 — raw extraction. (Steps 2–6: staging, quality gates, star schema, reconciliation, aggregates.)

## Run

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m src.extract --date 2026-09-01
```

Raw output lands in `data/raw/<date>.json` (git-ignored).

## Source
[Fire Department and EMS Dispatched Calls for Service](https://data.sf.gov/Public-Safety/Fire-Department-and-Emergency-Medical-Services-Dis/nuek-vuh3) — DataSF, PDDL license.
One row per *unit response*; multiple rows per call.

### Step 2 — load to staging
```bash
python -m src.load --date 2026-09-01
```
Reads `data/raw/<date>.json`, enforces the schema in `src/schema.py`, quarantines
unloadable rows to `staging_rejects` with a reason code, dedupes on `rowid`, and
writes to `staging_calls` in `sf911.db`. Re-running the same date replaces that
day's rows (idempotent).

### Step 3 — quality gates
```bash
python -m src.checks --date 2026-09-01
```
Runs every check in `src/checks.py` against that day's staging rows and records
each result in `dq_results`. `FAIL`-severity checks stop the pipeline (exit code 1);
`WARN` checks are recorded and reported but don't block.
