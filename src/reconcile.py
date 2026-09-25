"""
Step 5 — Reconcile: does what we loaded match what the source says exists?

Run:
    python -m src.reconcile --date 2026-09-01

Three comparisons per day, each written to `reconciliation`:
  api_vs_raw      : rows the API reports for the day vs rows in our raw file
  raw_vs_staging  : raw rows vs staging rows + rejects (nothing lost silently)
  staging_vs_fact : staging rows vs fact_unit_response rows (transform lost nothing)

The API count needs network. If it fails, we record SKIPPED, not a fake pass.
"""
import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone

import requests

import config
from src import db

log = logging.getLogger("reconcile")
TOLERANCE_PCT = 0.5   # allowed variance for api_vs_raw; the source revises history


def api_count(day: date) -> int | None:
    start = datetime.combine(day, datetime.min.time()).isoformat()
    end = datetime.combine(day + timedelta(days=1), datetime.min.time()).isoformat()
    try:
        r = requests.get(config.API_URL, params={
            "$select": "count(*) AS n",
            "$where": f"{config.DATE_COLUMN} >= '{start}' AND {config.DATE_COLUMN} < '{end}'"},
            headers={"User-Agent": config.USER_AGENT}, timeout=30)
        r.raise_for_status()
        return int(r.json()[0]["n"])
    except Exception as e:  # noqa: BLE001 - we want to record any failure, not crash
        log.warning("API count unavailable: %s", e)
        return None


def raw_count(day: date) -> int | None:
    p = config.RAW_DIR / f"{day.isoformat()}.json"
    if not p.exists():
        return None
    with p.open() as f:
        return len(json.load(f))


def run(day: date) -> list[tuple]:
    d = day.isoformat()
    rows = []
    with db.connect() as conn:
        cur = conn.cursor()

        def one(sql, params=()):
            cur.execute(db.q(sql), params)
            return cur.fetchone()[0]
        cur.execute("""CREATE TABLE IF NOT EXISTS reconciliation (
            load_date TEXT, comparison TEXT, source_count INTEGER, target_count INTEGER,
            variance_pct REAL, status TEXT, run_at TEXT)""")
        cur.execute(db.q("DELETE FROM reconciliation WHERE load_date=?"), (d,))

        staging = one("SELECT COUNT(*) FROM staging_calls WHERE load_date=?", (d,))
        rejects = one("SELECT COUNT(*) FROM staging_rejects WHERE load_date=?", (d,))
        # count facts by the day's staging rowids, not by load_date: a rowid re-seen on a
        # later day is (correctly) re-stamped with that later load_date
        fact = one("""SELECT COUNT(*) FROM staging_calls s
                      JOIN fact_unit_response f ON f.rowid_src = s.rowid
                      WHERE s.load_date=?""", (d,))
        raw = raw_count(day)
        api = api_count(day)

        def rec(name, src, tgt, tol):
            if src is None or tgt is None:
                rows.append((d, name, src, tgt, None, "SKIPPED"))
                return
            var = abs(src - tgt) / src * 100 if src else (0.0 if tgt == 0 else 100.0)
            rows.append((d, name, src, tgt, round(var, 3), "PASS" if var <= tol else "MISMATCH"))

        rec("api_vs_raw", api, raw, TOLERANCE_PCT)
        # raw may contain duplicates that dedupe removed; count them so nothing is "lost"
        dupes = 0
        if raw is not None:
            with (config.RAW_DIR / f"{d}.json").open() as f:
                ids = [r.get("rowid") for r in json.load(f)]
            dupes = len(ids) - len(set(ids))
        rec("raw_vs_staging", raw, staging + rejects + dupes, 0.0)
        rec("staging_vs_fact", staging, fact, 0.0)

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cur.executemany(db.q("INSERT INTO reconciliation VALUES (?,?,?,?,?,?,?)"), [r + (now,) for r in rows])
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile one day across pipeline layers.")
    parser.add_argument("--date", required=True)
    args = parser.parse_args(argv)
    rows = run(date.fromisoformat(args.date))
    print(f"\nReconciliation for {args.date}")
    print(f"{'comparison':<18} {'source':>8} {'target':>8} {'var%':>7}  status")
    for _, name, s, t, v, st in rows:
        print(f"{name:<18} {str(s):>8} {str(t):>8} {str(v):>7}  {st}")
    return 1 if any(r[5] == "MISMATCH" for r in rows) else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    sys.exit(main())
