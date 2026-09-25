"""
Step 3 — Quality gates on one day's staging data.

Run:
    python -m src.checks --date 2026-09-01

Every check writes a row to dq_results (pass or fail, with the observed value).
Checks have a severity:
  FAIL  -> the pipeline must stop; exit code 1. Downstream steps don't run.
  WARN  -> recorded and printed, but the pipeline continues.

Why write results even when they pass: a recruiter (or you, six months from now)
can see the history of every gate, every day. Silence is not evidence.
"""
import argparse
import logging
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone

import config

log = logging.getLogger("checks")

# Rough bounding box for San Francisco. Anything outside is a bad geocode.
SF_LON = (-123.2, -122.3)
SF_LAT = (37.6, 37.9)


@dataclass
class Result:
    name: str
    severity: str        # FAIL or WARN
    passed: bool
    observed: float
    threshold: str
    detail: str = ""


# ---------- individual checks ----------
# Each takes (conn, load_date) and returns a Result. Keep them small and single-purpose.

def check_row_count_nonzero(conn, d) -> Result:
    n = conn.execute("SELECT COUNT(*) FROM staging_calls WHERE load_date=?", (d,)).fetchone()[0]
    return Result("row_count_nonzero", "FAIL", n > 0, n, "> 0",
                  "Zero rows almost always means the API call failed, not a quiet day.")


def check_row_count_vs_history(conn, d) -> Result:
    """Today's count within 40% of the trailing 7-day average. WARN only until history exists."""
    n = conn.execute("SELECT COUNT(*) FROM staging_calls WHERE load_date=?", (d,)).fetchone()[0]
    hist = conn.execute(
        """SELECT AVG(c) FROM (
             SELECT COUNT(*) AS c FROM staging_calls
             WHERE load_date < ? GROUP BY load_date ORDER BY load_date DESC LIMIT 7)""",
        (d,)).fetchone()[0]
    if hist is None:
        return Result("row_count_vs_history", "WARN", True, n, "n/a", "No prior days loaded yet; skipped.")
    ratio = n / hist
    return Result("row_count_vs_history", "WARN", 0.6 <= ratio <= 1.4, round(ratio, 3),
                  "0.6 – 1.4 × trailing-7-day avg", f"today={n}, avg={hist:.0f}")


def check_no_duplicate_rowids(conn, d) -> Result:
    dupes = conn.execute(
        "SELECT COUNT(*) FROM (SELECT rowid FROM staging_calls WHERE load_date=? GROUP BY rowid HAVING COUNT(*)>1)",
        (d,)).fetchone()[0]
    return Result("no_duplicate_rowids", "FAIL", dupes == 0, dupes, "= 0")


def check_required_not_null(conn, d) -> Result:
    n = conn.execute(
        """SELECT COUNT(*) FROM staging_calls WHERE load_date=?
           AND (call_number IS NULL OR unit_id IS NULL OR received_dttm IS NULL)""",
        (d,)).fetchone()[0]
    return Result("required_not_null", "FAIL", n == 0, n, "= 0",
                  "Should be 0 because load.py quarantines these; if not, the loader is broken.")


def check_no_future_timestamps(conn, d) -> Result:
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
    n = conn.execute(
        """SELECT COUNT(*) FROM staging_calls WHERE load_date=?
           AND (received_dttm > ? OR dispatch_dttm > ? OR on_scene_dttm > ?)""",
        (d, now, now, now)).fetchone()[0]
    return Result("no_future_timestamps", "FAIL", n == 0, n, "= 0")


def check_timestamps_chronological(conn, d) -> Result:
    """received <= dispatch <= response <= on_scene, where each is present.
    Real data has a few violations (clock drift, manual entry); WARN above 2%."""
    total, bad = conn.execute(
        """SELECT COUNT(*),
                  SUM(CASE WHEN (dispatch_dttm IS NOT NULL AND dispatch_dttm < received_dttm)
                             OR (response_dttm IS NOT NULL AND dispatch_dttm IS NOT NULL AND response_dttm < dispatch_dttm)
                             OR (on_scene_dttm IS NOT NULL AND response_dttm IS NOT NULL AND on_scene_dttm < response_dttm)
                           THEN 1 ELSE 0 END)
           FROM staging_calls WHERE load_date=?""", (d,)).fetchone()
    pct = (bad or 0) / total * 100 if total else 0
    return Result("timestamps_chronological", "WARN", pct <= 2.0, round(pct, 2), "<= 2% of rows",
                  f"{bad} of {total} rows out of order")


def check_call_type_present(conn, d) -> Result:
    n = conn.execute(
        "SELECT COUNT(*) FROM staging_calls WHERE load_date=? AND (call_type IS NULL OR call_type='')",
        (d,)).fetchone()[0]
    return Result("call_type_present", "WARN", n == 0, n, "= 0")


def check_units_per_call_plausible(conn, d) -> Result:
    mx = conn.execute(
        """SELECT MAX(c) FROM (SELECT COUNT(*) AS c FROM staging_calls
           WHERE load_date=? GROUP BY call_number)""", (d,)).fetchone()[0] or 0
    return Result("units_per_call_plausible", "WARN", mx <= 30, mx, "<= 30 units on one call",
                  "A multi-alarm fire can legitimately exceed this; investigate, don't panic.")


def check_coordinates_in_sf(conn, d) -> Result:
    total, bad = conn.execute(
        """SELECT COUNT(*),
                  SUM(CASE WHEN longitude < ? OR longitude > ? OR latitude < ? OR latitude > ? THEN 1 ELSE 0 END)
           FROM staging_calls WHERE load_date=? AND longitude IS NOT NULL""",
        (*SF_LON, *SF_LAT, d)).fetchone()
    return Result("coordinates_in_sf", "WARN", (bad or 0) == 0, bad or 0, "= 0",
                  f"of {total} geocoded rows")


CHECKS = [
    check_row_count_nonzero,
    check_no_duplicate_rowids,
    check_required_not_null,
    check_no_future_timestamps,
    check_row_count_vs_history,
    check_timestamps_chronological,
    check_call_type_present,
    check_units_per_call_plausible,
    check_coordinates_in_sf,
]


# ---------- runner ----------

def record(conn, d, results: list[Result]) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS dq_results (
        load_date TEXT, check_name TEXT, severity TEXT, passed INTEGER,
        observed REAL, threshold TEXT, detail TEXT, run_at TEXT)""")
    conn.execute("DELETE FROM dq_results WHERE load_date=?", (d,))
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
    conn.executemany(
        "INSERT INTO dq_results VALUES (?,?,?,?,?,?,?,?)",
        [(d, r.name, r.severity, int(r.passed), r.observed, r.threshold, r.detail, now) for r in results])
    conn.commit()


def run(day: date) -> list[Result]:
    d = day.isoformat()
    with sqlite3.connect(config.DB_PATH) as conn:
        results = [chk(conn, d) for chk in CHECKS]
        record(conn, d, results)
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run quality checks on one day's staging data.")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args(argv)
    results = run(date.fromisoformat(args.date))

    print(f"\nQuality gates for {args.date}")
    print(f"{'check':<28} {'sev':<5} {'result':<6} {'observed':>10}   threshold")
    for r in results:
        status = "pass" if r.passed else "FAIL" if r.severity == "FAIL" else "warn"
        print(f"{r.name:<28} {r.severity:<5} {status:<6} {r.observed!s:>10}   {r.threshold}")
        if not r.passed and r.detail:
            print(f"    -> {r.detail}")

    hard_failures = [r for r in results if not r.passed and r.severity == "FAIL"]
    if hard_failures:
        print(f"\nSTOP: {len(hard_failures)} hard failure(s). Downstream steps must not run.")
        return 1
    print("\nOK: all hard gates passed.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    sys.exit(main())
