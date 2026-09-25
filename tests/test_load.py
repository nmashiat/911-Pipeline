
from src import load
from tests.conftest import DAY, columns, fetch, make_row, write_raw


def test_missing_call_number_is_quarantined_with_reason(sandbox):
    write_raw([make_row(), make_row(rowid="2-E01", call_number=None)])

    load.main(["--date", DAY.isoformat()])

    loaded = fetch("SELECT COUNT(*) FROM staging_calls")[0][0]
    rejects = fetch("SELECT rowid, reject_reason FROM staging_rejects")

    assert loaded == 1
    assert rejects == [("2-E01", "MISSING_CALL_NUMBER")]


def test_unparseable_timestamp_is_quarantined(sandbox):
    write_raw([make_row(rowid="3-E01", dispatch_dttm="not a date")])

    load.main(["--date", DAY.isoformat()])

    rejects = fetch("SELECT reject_reason FROM staging_rejects")
    assert rejects == [("UNPARSEABLE_DISPATCH_DTTM",)]


def test_duplicate_rowid_keeps_latest(sandbox):
    older = make_row(data_as_of="2026-09-01T03:00:00.000", on_scene_dttm=None)
    newer = make_row(data_as_of="2026-09-01T04:00:00.000")
    write_raw([older, newer])

    load.main(["--date", DAY.isoformat()])

    rows = fetch("SELECT on_scene_dttm FROM staging_calls")
    assert str(rows[0][0]).replace(" ", "T") == "2026-09-01T03:25:00"


def test_missing_optional_column_is_created(sandbox):
    """API omits null fields; a day with no hospital_dttm must still have the column."""
    write_raw([make_row(hospital_dttm=None)])

    load.main(["--date", DAY.isoformat()])

    assert "hospital_dttm" in columns("staging_calls")


def test_rerun_is_idempotent(sandbox):
    write_raw([make_row(), make_row(rowid="2-E02", unit_id="E02")])

    load.main(["--date", DAY.isoformat()])
    load.main(["--date", DAY.isoformat()])

    assert fetch("SELECT COUNT(*) FROM staging_calls")[0][0] == 2
