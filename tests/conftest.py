"""
Shared fixtures. Each test gets its own temp folders and its own SQLite file,
so tests never touch real data and can run in any order.
"""
import json
from datetime import date
from pathlib import Path

import pytest

import config


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


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch):
    """Redirect RAW_DIR and DB_PATH into a temp folder for the duration of one test."""
    raw = tmp_path / "raw"
    raw.mkdir()
    monkeypatch.setattr(config, "RAW_DIR", raw)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    return tmp_path


def write_raw(rows: list[dict], day: date = DAY) -> None:
    with (config.RAW_DIR / f"{day.isoformat()}.json").open("w") as f:
        json.dump(rows, f)
