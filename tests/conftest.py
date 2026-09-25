"""
Shared fixtures. Each test gets its own temp folders and its own SQLite file,
so tests never touch real data and can run in any order.
"""
import json
from datetime import date
from pathlib import Path

import pytest

import config
from src import db


BASE_ROW = {
    "rowid": "1-E01", "call_number": "1", "incident_number": "9",
    "unit_id": "E01", "unit_type": "ENGINE",
    "call_type": "Medical Incident", "call_type_group": "Potentially Life-Threatening",
    "call_final_disposition": "Code 2 Transport",
    "original_priority": "3", "priority": "3", "final_priority": "3",
    "address": "300 Block of 4TH ST", "city": "San Francisco", "zipcode_of_incident": "94107",
    "battalion": "B03", "station_area": "08", "box": "2215",
    "fire_prevention_district": "3", "supervisor_district": "6",
    "neighborhoods_analysis_boundaries": "South of Market",
    "number_of_alarms": "1", "unit_sequence_in_call_dispatch": "1", "als_unit": False,
    "call_date": "2026-09-01T00:00:00.000", "watch_date": "2026-08-31T00:00:00.000",
    "received_dttm": "2026-09-01T03:20:11.000", "entry_dttm": "2026-09-01T03:21:00.000",
    "dispatch_dttm": "2026-09-01T03:22:00.000", "response_dttm": "2026-09-01T03:23:00.000",
    "on_scene_dttm": "2026-09-01T03:25:00.000", "available_dttm": "2026-09-01T03:40:00.000",
    "case_location": {"type": "Point", "coordinates": [-122.401, 37.782]},
    "data_as_of": "2026-09-01T03:27:08.000", "data_loaded_at": "2026-09-02T04:03:20.000",
}

DAY = date(2026, 9, 1)


def make_row(**overrides) -> dict:
    """A valid row, with any fields overridden. Pass field=None to delete it (API omits nulls)."""
    row = dict(BASE_ROW)
    for k, v in overrides.items():
        if v is None:
            row.pop(k, None)
        else:
            row[k] = v
    return row


ALL_TABLES = ["agg_daily", "reconciliation", "dq_results", "fact_call", "fact_unit_response",
              "dim_neighborhood", "dim_unit", "dim_call_type", "dim_date",
              "staging_rejects", "staging_calls"]


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch):
    """
    Isolate one test: RAW_DIR in a temp folder, and a fresh database.
    SQLite: a new file per test. Postgres (SF911_DB=postgres): drop every table first.
    """
    raw = tmp_path / "raw"
    raw.mkdir()
    monkeypatch.setattr(config, "RAW_DIR", raw)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    if db.is_postgres():
        with db.connect() as conn:
            cur = conn.cursor()
            for t in ALL_TABLES:
                cur.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    return tmp_path


def fetch(sql: str, params=()) -> list[tuple]:
    """Run a query on whichever backend is active and return all rows."""
    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute(db.q(sql), params)
        return cur.fetchall()


def columns(table: str) -> list[str]:
    if db.is_postgres():
        return [r[0] for r in fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?", (table,))]
    return [r[1] for r in fetch(f"PRAGMA table_info({table})")]


def write_raw(rows: list[dict], day: date = DAY) -> None:
    with (config.RAW_DIR / f"{day.isoformat()}.json").open("w") as f:
        json.dump(rows, f)
