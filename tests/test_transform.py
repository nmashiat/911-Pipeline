from src import load, transform
from tests.conftest import DAY, fetch, make_row, write_raw


def test_null_call_type_group_does_not_duplicate_dimension(sandbox):
    """
    Two units on calls whose call_type_group is NULL must share ONE dim_call_type row.
    Postgres treats NULLs as distinct in UNIQUE constraints unless told otherwise,
    which fanned out facts on the join. Regression for CardinalityViolation on real data.
    """
    write_raw([
        make_row(rowid="a-E01", call_number="a", call_type="Alarms", call_type_group=None),
        make_row(rowid="b-E02", call_number="b", unit_id="E02", call_type="Alarms", call_type_group=None),
    ])
    load.main(["--date", DAY.isoformat()])
    transform.main(["--date", DAY.isoformat()])
    transform.main(["--date", DAY.isoformat()])  # second run must not add dim rows either

    assert fetch("SELECT COUNT(*) FROM dim_call_type WHERE call_type='Alarms'")[0][0] == 1
    assert fetch("SELECT COUNT(*) FROM fact_unit_response")[0][0] == 2
    assert fetch("SELECT COUNT(*) FROM fact_call")[0][0] == 2


def test_null_unit_type_does_not_duplicate_dimension(sandbox):
    write_raw([make_row(rowid="a-X1", call_number="a", unit_id="X1", unit_type=None),
               make_row(rowid="b-X1", call_number="b", unit_id="X1", unit_type=None)])
    load.main(["--date", DAY.isoformat()])
    transform.main(["--date", DAY.isoformat()])
    assert fetch("SELECT COUNT(*) FROM dim_unit WHERE unit_id='X1'")[0][0] == 1
    assert fetch("SELECT COUNT(*) FROM fact_unit_response")[0][0] == 2


def test_response_time_is_first_unit_on_scene(sandbox):
    write_raw([
        make_row(rowid="c-E01", call_number="c", received_dttm="2026-09-01T10:00:00.000",
                 dispatch_dttm="2026-09-01T10:01:00.000", on_scene_dttm="2026-09-01T10:08:00.000"),
        make_row(rowid="c-E02", call_number="c", unit_id="E02", received_dttm="2026-09-01T10:00:00.000",
                 dispatch_dttm="2026-09-01T10:01:00.000", on_scene_dttm="2026-09-01T10:05:00.000"),
    ])
    load.main(["--date", DAY.isoformat()])
    transform.main(["--date", DAY.isoformat()])
    row = fetch("SELECT units_dispatched, units_on_scene, response_secs FROM fact_call WHERE call_number='c'")[0]
    assert tuple(row) == (2, 2, 300)


def test_out_of_order_interval_is_null_not_negative(sandbox):
    write_raw([make_row(rowid="d-E01", call_number="d", on_scene_dttm="2026-09-01T03:00:00.000")])
    load.main(["--date", DAY.isoformat()])
    transform.main(["--date", DAY.isoformat()])
    assert fetch("SELECT secs_to_scene FROM fact_unit_response")[0][0] is None
