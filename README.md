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
