"""
Step 6 — Daily aggregates for BI, plus a small CSV export that is safe to commit.

Run:
    python -m src.aggregate --date 2026-09-01

agg_daily: one row per (date, call_type_group, neighborhood) with call volume and
response-time stats. outputs/daily_summary.csv is the same at date grain only —
small enough to commit, so the repo shows the pipeline running.
"""
import argparse
import csv
import logging
import sys
from datetime import date

import config
from src import db

log = logging.getLogger("aggregate")
OUT = config.ROOT / "outputs"


def build(day: date) -> int:
    d = day.isoformat()
    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS agg_daily (
            full_date TEXT, call_type_group TEXT, neighborhood TEXT,
            calls INTEGER, units INTEGER,
            avg_response_secs REAL, p90_response_secs INTEGER, pct_calls_with_on_scene REAL,
            load_date TEXT)""")
        cur.execute(db.q("DELETE FROM agg_daily WHERE load_date=?"), (d,))
        cur.execute(db.q("""
            INSERT INTO agg_daily
            WITH base AS (
              SELECT CAST(dd.full_date AS TEXT) AS full_date, COALESCE(ct.call_type_group,'(none)') AS grp,
                     COALESCE(n.neighborhood,'(none)') AS hood,
                     fc.response_secs, fc.units_dispatched, fc.load_date
              FROM fact_call fc
              JOIN dim_date dd ON dd.date_key = fc.date_key
              LEFT JOIN dim_call_type ct ON ct.call_type_key = fc.call_type_key
              LEFT JOIN dim_neighborhood n ON n.neighborhood_key = fc.neighborhood_key
              WHERE fc.load_date = ?),
            ranked AS (
              SELECT *, ROW_NUMBER() OVER (PARTITION BY full_date, grp, hood ORDER BY response_secs) AS rn,
                     COUNT(response_secs) OVER (PARTITION BY full_date, grp, hood) AS n_resp
              FROM base)
            SELECT full_date, grp, hood,
                   COUNT(*), SUM(units_dispatched),
                   ROUND(CAST(AVG(response_secs) AS NUMERIC), 1),
                   MAX(CASE WHEN rn = CAST(n_resp * 0.9 + 0.5 AS INTEGER) THEN response_secs END),
                   ROUND(100.0 * COUNT(response_secs) / COUNT(*), 1),
                   MAX(load_date)
            FROM ranked GROUP BY full_date, grp, hood"""), (d,))

        # committable summary: whole history at date grain
        OUT.mkdir(exist_ok=True)
        cur.execute("""
            SELECT full_date, SUM(calls) AS calls, SUM(units) AS units,
                   ROUND(CAST(SUM(avg_response_secs*calls)/SUM(calls) AS NUMERIC),1) AS avg_response_secs
            FROM agg_daily GROUP BY full_date ORDER BY full_date""")
        rows = cur.fetchall()
        with (OUT / "daily_summary.csv").open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "calls", "units", "avg_response_secs"])
            w.writerows(rows)
        cur.execute(db.q("SELECT COUNT(*) FROM agg_daily WHERE load_date=?"), (d,))
        n = cur.fetchone()[0]
    return n


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args(argv)
    n = build(date.fromisoformat(args.date))
    print(f"\nagg_daily rows for {args.date}: {n}; summary -> outputs/daily_summary.csv")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    sys.exit(main())
