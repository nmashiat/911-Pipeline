"""
Step 4 — Build the star schema from staging for one day.

Run:
    python -m src.transform --date 2026-09-01

Dimensions are upserted (INSERT OR IGNORE): a call type seen before keeps its key.
Facts for the day are deleted then re-inserted, so reruns are idempotent.
Interval columns are NULL when the order is invalid rather than negative —
we don't want a -300 second response time averaging into a report.
"""
import argparse
import logging
import sqlite3
import sys
from datetime import date

import config
from src.load import DB_PATH

log = logging.getLogger("transform")
DDL_PATH = config.ROOT / "sql" / "star_schema.sql"

SECS = "CAST((julianday({b}) - julianday({a})) * 86400 AS INTEGER)"
VALID = "({a} IS NOT NULL AND {b} IS NOT NULL AND {b} >= {a})"


def interval(a: str, b: str) -> str:
    return f"CASE WHEN {VALID.format(a=a, b=b)} THEN {SECS.format(a=a, b=b)} END"


def build(day: date) -> dict:
    d = day.isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(DDL_PATH.read_text())

        # ---- dimensions: insert anything new, keep existing keys ----
        conn.execute("""
            INSERT OR IGNORE INTO dim_date
            SELECT DISTINCT CAST(strftime('%Y%m%d', received_dttm) AS INTEGER),
                   date(received_dttm),
                   CAST(strftime('%Y', received_dttm) AS INTEGER),
                   CAST(strftime('%m', received_dttm) AS INTEGER),
                   CAST(strftime('%d', received_dttm) AS INTEGER),
                   CAST(strftime('%w', received_dttm) AS INTEGER),
                   CASE WHEN strftime('%w', received_dttm) IN ('0','6') THEN 1 ELSE 0 END
            FROM staging_calls WHERE load_date = ?""", (d,))
        conn.execute("""
            INSERT OR IGNORE INTO dim_call_type (call_type, call_type_group)
            SELECT DISTINCT call_type, call_type_group FROM staging_calls
            WHERE load_date = ? AND call_type IS NOT NULL""", (d,))
        conn.execute("""
            INSERT OR IGNORE INTO dim_unit (unit_id, unit_type)
            SELECT DISTINCT unit_id, unit_type FROM staging_calls WHERE load_date = ?""", (d,))
        conn.execute("""
            INSERT OR IGNORE INTO dim_neighborhood (neighborhood, supervisor_district, battalion)
            SELECT neighborhoods_analysis_boundaries, MIN(supervisor_district), MIN(battalion)
            FROM staging_calls WHERE load_date = ? AND neighborhoods_analysis_boundaries IS NOT NULL
            GROUP BY 1""", (d,))

        # ---- fact_unit_response ----
        conn.execute("DELETE FROM fact_unit_response WHERE load_date = ?", (d,))
        # A rowid already present under ANOTHER load_date means the source moved or
        # revised a record. Latest load wins; we log it so it can be investigated.
        collisions = conn.execute("""
            SELECT COUNT(*) FROM staging_calls s
            JOIN fact_unit_response f ON f.rowid_src = s.rowid
            WHERE s.load_date = ? AND f.load_date <> ?""", (d, d)).fetchone()[0]
        if collisions:
            log.warning("%d rowid(s) already loaded under a different day; replacing with %s", collisions, d)
        conn.execute(f"""
            INSERT OR REPLACE INTO fact_unit_response
            SELECT s.rowid, s.call_number,
                   CAST(strftime('%Y%m%d', s.received_dttm) AS INTEGER),
                   ct.call_type_key, u.unit_key, n.neighborhood_key,
                   s.received_dttm, s.dispatch_dttm, s.on_scene_dttm, s.available_dttm,
                   s.priority, s.als_unit, s.unit_sequence_in_call_dispatch,
                   {interval('s.received_dttm', 's.dispatch_dttm')},
                   {interval('s.dispatch_dttm', 's.on_scene_dttm')},
                   {interval('s.received_dttm', 's.on_scene_dttm')},
                   s.load_date
            FROM staging_calls s
            LEFT JOIN dim_call_type ct ON ct.call_type = s.call_type
                                      AND COALESCE(ct.call_type_group,'') = COALESCE(s.call_type_group,'')
            LEFT JOIN dim_unit u ON u.unit_id = s.unit_id AND COALESCE(u.unit_type,'') = COALESCE(s.unit_type,'')
            LEFT JOIN dim_neighborhood n ON n.neighborhood = s.neighborhoods_analysis_boundaries
            WHERE s.load_date = ?""", (d,))

        # ---- fact_call: roll up units to calls ----
        # A call can have units under more than one load_date (e.g. spans midnight).
        # Rebuild every call touched today from ALL its unit rows, not just today's.
        conn.execute("""
            DELETE FROM fact_call WHERE load_date = ?
               OR call_number IN (SELECT call_number FROM fact_unit_response WHERE load_date = ?)""", (d, d))
        conn.execute(f"""
            INSERT INTO fact_call
            SELECT call_number,
                   MIN(date_key),
                   MIN(call_type_key),
                   MIN(neighborhood_key),
                   MIN(received_dttm),
                   MIN(dispatch_dttm),
                   MIN(on_scene_dttm),
                   COUNT(*),
                   SUM(CASE WHEN on_scene_dttm IS NOT NULL THEN 1 ELSE 0 END),
                   MAX(priority),
                   {interval('MIN(received_dttm)', 'MIN(on_scene_dttm)')},
                   ?
            FROM fact_unit_response
            WHERE call_number IN (SELECT call_number FROM fact_unit_response WHERE load_date = ?)
            GROUP BY call_number""", (d, d))
        conn.commit()

        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t} WHERE load_date=?", (d,)).fetchone()[0]
                  for t in ("fact_unit_response", "fact_call")}
        counts.update({t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                       for t in ("dim_date", "dim_call_type", "dim_unit", "dim_neighborhood")})
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build star schema for one day.")
    parser.add_argument("--date", required=True)
    args = parser.parse_args(argv)
    counts = build(date.fromisoformat(args.date))
    print(f"\nStar schema for {args.date}:")
    for k, v in counts.items():
        print(f"  {k:<22} {v:>8}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    sys.exit(main())
