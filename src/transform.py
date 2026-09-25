"""
Step 4 — Build the star schema from staging for one day.

Run:
    python -m src.transform --date 2026-09-01

Works on SQLite (default) and Postgres (SF911_DB=postgres). Dialect differences
are isolated in src/db.py; the SQL here is written once.

Dimensions are upserted: a call type seen before keeps its key. Nullable parts of
a dimension's natural key (call_type_group, unit_type) are stored as '' — both
SQLite and Postgres treat NULLs as distinct in UNIQUE constraints, which would
create a new dimension row on every load and fan out the facts on the join.
Facts for the day are deleted then re-inserted, so reruns are idempotent.
Interval columns are NULL when the order is invalid rather than negative —
we don't want a -300 second response time averaging into a report.
"""
import argparse
import logging
import sys
from datetime import date

import config
from src import db

log = logging.getLogger("transform")

VALID = "({a} IS NOT NULL AND {b} IS NOT NULL AND {b} >= {a})"

FUR_COLS = ["rowid_src", "call_number", "date_key", "call_type_key", "unit_key", "neighborhood_key",
            "received_dttm", "dispatch_dttm", "on_scene_dttm", "available_dttm", "priority", "als_unit",
            "unit_sequence", "secs_to_dispatch", "secs_dispatch_to_scene", "secs_to_scene", "load_date"]


def ddl_path():
    name = "star_schema_postgres.sql" if db.is_postgres() else "star_schema.sql"
    return config.ROOT / "sql" / name


def interval(a: str, b: str) -> str:
    return f"CASE WHEN {VALID.format(a=a, b=b)} THEN {db.secs_between(a, b)} END"


def date_parts(ts: str) -> str:
    if db.is_postgres():
        return f"""{ts}::date,
                   EXTRACT(YEAR FROM {ts})::int, EXTRACT(MONTH FROM {ts})::int,
                   EXTRACT(DAY FROM {ts})::int, EXTRACT(DOW FROM {ts})::int,
                   CASE WHEN EXTRACT(DOW FROM {ts}) IN (0,6) THEN 1 ELSE 0 END"""
    return f"""date({ts}),
                   CAST(strftime('%Y', {ts}) AS INTEGER),
                   CAST(strftime('%m', {ts}) AS INTEGER),
                   CAST(strftime('%d', {ts}) AS INTEGER),
                   CAST(strftime('%w', {ts}) AS INTEGER),
                   CASE WHEN strftime('%w', {ts}) IN ('0','6') THEN 1 ELSE 0 END"""


def build(day: date) -> dict:
    d = day.isoformat()
    with db.connect() as conn:
        db.executescript(conn, ddl_path().read_text())
        cur = conn.cursor()

        def run(sql: str, params=()):
            cur.execute(db.q(sql), params)

        # ---- dimensions: insert anything new, keep existing keys ----
        run(f"""
            INSERT OR IGNORE INTO dim_date
            SELECT DISTINCT {db.date_key('received_dttm')}, {date_parts('received_dttm')}
            FROM staging_calls WHERE load_date = ?
            {db.on_conflict_ignore('date_key')}""", (d,))
        run(f"""
            INSERT OR IGNORE INTO dim_call_type (call_type, call_type_group)
            SELECT DISTINCT call_type, COALESCE(call_type_group, '') FROM staging_calls
            WHERE load_date = ? AND call_type IS NOT NULL
            {db.on_conflict_ignore('call_type, call_type_group')}""", (d,))
        run(f"""
            INSERT OR IGNORE INTO dim_unit (unit_id, unit_type)
            SELECT DISTINCT unit_id, COALESCE(unit_type, '') FROM staging_calls WHERE load_date = ?
            {db.on_conflict_ignore('unit_id, unit_type')}""", (d,))
        run(f"""
            INSERT OR IGNORE INTO dim_neighborhood (neighborhood, supervisor_district, battalion)
            SELECT neighborhoods_analysis_boundaries, MIN(supervisor_district), MIN(battalion)
            FROM staging_calls WHERE load_date = ? AND neighborhoods_analysis_boundaries IS NOT NULL
            GROUP BY 1
            {db.on_conflict_ignore('neighborhood')}""", (d,))

        # ---- fact_unit_response ----
        run("DELETE FROM fact_unit_response WHERE load_date = ?", (d,))
        # A rowid already present under ANOTHER load_date means the source moved or
        # revised a record. Latest load wins; we log it so it can be investigated.
        run("""
            SELECT COUNT(*) FROM staging_calls s
            JOIN fact_unit_response f ON f.rowid_src = s.rowid
            WHERE s.load_date = ? AND f.load_date <> ?""", (d, d))
        collisions = cur.fetchone()[0]
        if collisions:
            log.warning("%d rowid(s) already loaded under a different day; replacing with %s", collisions, d)
        run(f"""
            INSERT OR REPLACE INTO fact_unit_response ({', '.join(FUR_COLS)})
            SELECT s.rowid, s.call_number,
                   {db.date_key('s.received_dttm')},
                   ct.call_type_key, u.unit_key, n.neighborhood_key,
                   s.received_dttm, s.dispatch_dttm, s.on_scene_dttm, s.available_dttm,
                   s.priority, s.als_unit, s.unit_sequence_in_call_dispatch,
                   {interval('s.received_dttm', 's.dispatch_dttm')},
                   {interval('s.dispatch_dttm', 's.on_scene_dttm')},
                   {interval('s.received_dttm', 's.on_scene_dttm')},
                   s.load_date
            FROM staging_calls s
            LEFT JOIN dim_call_type ct ON ct.call_type = s.call_type
                                      AND ct.call_type_group = COALESCE(s.call_type_group, '')
            LEFT JOIN dim_unit u ON u.unit_id = s.unit_id AND u.unit_type = COALESCE(s.unit_type, '')
            LEFT JOIN dim_neighborhood n ON n.neighborhood = s.neighborhoods_analysis_boundaries
            WHERE s.load_date = ?
            {db.on_conflict_replace('rowid_src', FUR_COLS[1:])}""", (d,))

        # ---- fact_call: roll up units to calls ----
        # A call can have units under more than one load_date (e.g. spans midnight).
        # Rebuild every call touched today from ALL its unit rows, not just today's.
        run("""
            DELETE FROM fact_call WHERE load_date = ?
               OR call_number IN (SELECT call_number FROM fact_unit_response WHERE load_date = ?)""", (d, d))
        run(f"""
            INSERT INTO fact_call
            SELECT call_number,
                   MIN(date_key), MIN(call_type_key), MIN(neighborhood_key),
                   MIN(received_dttm), MIN(dispatch_dttm), MIN(on_scene_dttm),
                   COUNT(*),
                   SUM(CASE WHEN on_scene_dttm IS NOT NULL THEN 1 ELSE 0 END),
                   MAX(priority),
                   {interval('MIN(received_dttm)', 'MIN(on_scene_dttm)')},
                   ?
            FROM fact_unit_response
            WHERE call_number IN (SELECT call_number FROM fact_unit_response WHERE load_date = ?)
            GROUP BY call_number""", (d, d))

        counts = {}
        for t in ("fact_unit_response", "fact_call"):
            run(f"SELECT COUNT(*) FROM {t} WHERE load_date=?", (d,))
            counts[t] = cur.fetchone()[0]
        for t in ("dim_date", "dim_call_type", "dim_unit", "dim_neighborhood"):
            run(f"SELECT COUNT(*) FROM {t}")
            counts[t] = cur.fetchone()[0]
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build star schema for one day.")
    parser.add_argument("--date", required=True)
    args = parser.parse_args(argv)
    counts = build(date.fromisoformat(args.date))
    print(f"\nStar schema for {args.date} [{db.BACKEND}]:")
    for k, v in counts.items():
        print(f"  {k:<22} {v:>8}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    sys.exit(main())
