"""
Step 2 — Load one day's raw JSON into a typed, deduplicated staging table.

Run:
    python -m src.load --date 2026-09-01

What this does, in order:
  1. Read the raw file for the day (never modify it).
  2. Force the declared schema: every expected column exists, correctly typed.
  3. Quarantine rows that can't be loaded, with a reason code. Never drop silently.
  4. Deduplicate on rowid (keep the last occurrence — newest API state).
  5. Write to SQLite, replacing any earlier load of the same day (idempotent).
"""
import argparse
import json
import logging
import sys
from datetime import date

import pandas as pd

import config
from src import db, schema

log = logging.getLogger("load")



# ---------- 1. read ----------

def read_raw(day: date) -> pd.DataFrame:
    path = config.RAW_DIR / f"{day.isoformat()}.json"
    if not path.exists():
        raise FileNotFoundError(f"No raw file for {day}. Run src.extract first: {path}")
    with path.open() as f:
        rows = json.load(f)
    log.info("read %d raw rows from %s", len(rows), path)
    return pd.DataFrame(rows)


# ---------- 2. conform to schema ----------

def flatten_geo(df: pd.DataFrame) -> pd.DataFrame:
    """case_location -> longitude, latitude. Missing geo is allowed."""
    def coords(v):
        if isinstance(v, dict) and isinstance(v.get("coordinates"), list) and len(v["coordinates"]) == 2:
            return v["coordinates"]
        return [None, None]

    if schema.GEO_SOURCE in df.columns:
        pairs = df[schema.GEO_SOURCE].apply(coords)
        df["longitude"] = pairs.str[0].astype(float)
        df["latitude"] = pairs.str[1].astype(float)
        df = df.drop(columns=[schema.GEO_SOURCE])
    else:
        df["longitude"] = None
        df["latitude"] = None
    return df


def conform(df: pd.DataFrame) -> pd.DataFrame:
    """Guarantee every declared column exists with the declared type."""
    df = flatten_geo(df)

    # Add any column the API didn't send today (e.g. hospital_dttm on a quiet day)
    for col in schema.ALL_COLUMNS:
        if col not in df.columns:
            df[col] = None

    # Drop anything the API sent that we haven't declared — surface it in the log
    extra = [c for c in df.columns if c not in schema.ALL_COLUMNS]
    if extra:
        log.warning("undeclared columns from API, ignored: %s", extra)
        df = df.drop(columns=extra)

    for col in schema.TIMESTAMP_COLUMNS:
        df[col] = pd.to_datetime(df[col], errors="coerce")  # bad -> NaT, caught below
    for col in schema.DATE_COLUMNS:
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    for col in schema.INT_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in schema.BOOL_COLUMNS:
        df[col] = df[col].map({True: True, False: False, "true": True, "false": False})
    for col in schema.TEXT_COLUMNS + schema.KEY_COLUMNS:
        df[col] = df[col].astype("string").str.strip()

    return df[schema.ALL_COLUMNS]


# ---------- 3. quarantine ----------

def split_rejects(df: pd.DataFrame, raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Return (good_rows, rejected_rows). Each rejected row carries a reason code.
    A row can fail for several reasons; we record the first one found.
    """
    reason = pd.Series([None] * len(df), index=df.index, dtype="object")

    for col in schema.REQUIRED_COLUMNS:
        missing = df[col].isna() & reason.isna()
        reason[missing] = f"MISSING_{col.upper()}"

    # Timestamp present in raw but failed to parse -> reject (we must not guess)
    for col in schema.TIMESTAMP_COLUMNS:
        if col in raw.columns:
            unparseable = raw[col].notna() & df[col].isna() & reason.isna()
            reason[unparseable] = f"UNPARSEABLE_{col.upper()}"

    good = df[reason.isna()].copy()
    bad = df[reason.notna()].copy()
    bad["reject_reason"] = reason[reason.notna()]

    if len(bad):
        log.warning("quarantined %d rows: %s", len(bad), bad["reject_reason"].value_counts().to_dict())
    return good, bad


# ---------- 4. dedupe ----------

def dedupe(df: pd.DataFrame) -> pd.DataFrame:
    before = len(df)
    df = df.sort_values("data_as_of").drop_duplicates(subset=schema.KEY_COLUMNS, keep="last")
    dropped = before - len(df)
    if dropped:
        log.info("removed %d duplicate rowids (kept latest data_as_of)", dropped)
    return df


# ---------- 5. write ----------

def create_table_sql(table: str, extra: str = "") -> str:
    """Explicit DDL so the table shape is declared, not inferred from whatever loads first."""
    ts = "TIMESTAMP" if db.is_postgres() else "TEXT"
    dt = "DATE" if db.is_postgres() else "TEXT"
    cols = [f"{c} TEXT" for c in schema.KEY_COLUMNS + schema.TEXT_COLUMNS]
    cols += [f"{c} {ts}" for c in schema.TIMESTAMP_COLUMNS]
    cols += [f"{c} {dt}" for c in schema.DATE_COLUMNS]
    cols += [f"{c} INTEGER" for c in schema.INT_COLUMNS + schema.BOOL_COLUMNS]
    cols += [f"{c} REAL" for c in schema.GEO_COLUMNS]
    return f"CREATE TABLE IF NOT EXISTS {table} ({extra} {', '.join(cols)}, load_date TEXT)"


def _rows(df: pd.DataFrame) -> list[tuple]:
    """DataFrame -> list of tuples with NaN/NaT/pd.NA turned into None."""
    return [tuple(None if pd.isna(v) else v for v in row) for row in df.itertuples(index=False, name=None)]


def write(day: date, good: pd.DataFrame, bad: pd.DataFrame) -> None:
    good = good.copy()
    bad = bad.copy()
    good["load_date"] = day.isoformat()
    bad["load_date"] = day.isoformat()

    for df in (good, bad):
        for col in schema.TIMESTAMP_COLUMNS:
            # Postgres takes real datetimes; SQLite stores ISO text
            df[col] = df[col] if db.is_postgres() else df[col].dt.strftime("%Y-%m-%dT%H:%M:%S")
            df[col] = df[col].astype(object).where(df[col].notna(), None)
        for col in schema.DATE_COLUMNS:
            df[col] = df[col] if db.is_postgres() else df[col].astype("string")
        for col in schema.BOOL_COLUMNS:
            df[col] = df[col].map({True: 1, False: 0}).astype("Int64")

    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute(create_table_sql("staging_calls"))
        cur.execute(create_table_sql("staging_rejects", extra="reject_reason TEXT,"))
        for table in ("staging_calls", "staging_rejects"):
            cur.execute(db.q(f"DELETE FROM {table} WHERE load_date = ?"), (day.isoformat(),))
        for table, df in (("staging_calls", good), ("staging_rejects", bad)):
            if len(df):
                cols = ", ".join(df.columns)
                ph = ", ".join(["?"] * len(df.columns))
                cur.executemany(db.q(f"INSERT INTO {table} ({cols}) VALUES ({ph})"), _rows(df))

    log.info("wrote %d rows to staging_calls, %d to staging_rejects (%s)", len(good), len(bad), db.BACKEND)


# ---------- main ----------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Load one day of raw data into staging.")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args(argv)
    day = date.fromisoformat(args.date)

    raw = read_raw(day)
    df = conform(raw.copy())
    good, bad = split_rejects(df, raw)
    good = dedupe(good)
    write(day, good, bad)

    print(f"\nSummary for {day}: raw={len(raw)} loaded={len(good)} rejected={len(bad)}")
    print("Calls (distinct call_number):", good["call_number"].nunique())
    print("Units per call (mean):", round(len(good) / max(good["call_number"].nunique(), 1), 2))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    sys.exit(main())
