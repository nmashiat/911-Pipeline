"""
One place that knows how to open a database connection.

    SF911_DB=sqlite     (default)  -> sf911.db file, zero setup
    SF911_DB=postgres              -> docker-compose Postgres, or SF911_DSN

Every module calls db.connect() and writes SQL that works on both engines.
The few places where dialects differ are handled here (placeholders, upsert,
datetime maths) so the pipeline code stays readable.
"""
import os
import sqlite3
from contextlib import contextmanager

import config

BACKEND = os.environ.get("SF911_DB", "sqlite").lower()
DSN = os.environ.get("SF911_DSN", "postgresql://sf911:sf911@localhost:5432/sf911")


def is_postgres() -> bool:
    return BACKEND == "postgres"


@contextmanager
def connect():
    """Yield a DB-API connection; commits on success, rolls back on error."""
    if is_postgres():
        import psycopg
        conn = psycopg.connect(DSN)
    else:
        conn = sqlite3.connect(config.DB_PATH)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def q(sql: str) -> str:
    """Translate the tiny set of SQLite-isms we use into Postgres when needed."""
    if not is_postgres():
        return sql
    return (sql
            .replace("?", "%s")
            .replace("INSERT OR IGNORE INTO", "INSERT INTO")
            .replace("INSERT OR REPLACE INTO", "INSERT INTO"))


# --- dialect helpers used by transform.py ---------------------------------

def secs_between(a: str, b: str) -> str:
    """SQL expression: whole seconds from timestamp a to timestamp b."""
    if is_postgres():
        return f"CAST(EXTRACT(EPOCH FROM ({b}::timestamp - {a}::timestamp)) AS INTEGER)"
    return f"CAST((julianday({b}) - julianday({a})) * 86400 AS INTEGER)"


def date_key(ts: str) -> str:
    if is_postgres():
        return f"CAST(TO_CHAR({ts}::timestamp, 'YYYYMMDD') AS INTEGER)"
    return f"CAST(strftime('%Y%m%d', {ts}) AS INTEGER)"


def on_conflict_ignore(cols: str) -> str:
    return f" ON CONFLICT ({cols}) DO NOTHING" if is_postgres() else ""


def on_conflict_replace(key: str, cols: list[str]) -> str:
    if not is_postgres():
        return ""
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols)
    return f" ON CONFLICT ({key}) DO UPDATE SET {sets}"


def executescript(conn, script: str) -> None:
    """Run a multi-statement DDL file on either engine."""
    if is_postgres():
        with conn.cursor() as cur:
            cur.execute(script)
    else:
        conn.executescript(script)


def ts_param() -> str:
    """Placeholder for a timestamp parameter: Postgres needs an explicit cast from text."""
    return "CAST(? AS TIMESTAMP)" if is_postgres() else "?"
