
from src import checks, load
from tests.conftest import DAY, fetch, make_row, write_raw


def _load(rows):
    write_raw(rows)
    load.main(["--date", DAY.isoformat()])


def _results():
    return {r.name: r for r in checks.run(DAY)}


def test_future_timestamp_fails_hard_gate(sandbox):
    _load([make_row(rowid="f-1", received_dttm="2099-01-01T00:00:00.000")])

    r = _results()["no_future_timestamps"]
    assert r.severity == "FAIL"
    assert r.passed is False
    assert r.observed == 1


def test_clean_day_passes_all_hard_gates(sandbox):
    _load([make_row(), make_row(rowid="2-E02", unit_id="E02")])

    hard = [r for r in checks.run(DAY) if r.severity == "FAIL"]
    assert hard and all(r.passed for r in hard)


def test_out_of_order_timestamps_warn_not_fail(sandbox):
    # on_scene before dispatch on 1 of 1 rows = 100% > 2% threshold
    _load([make_row(on_scene_dttm="2026-09-01T03:00:00.000")])

    r = _results()["timestamps_chronological"]
    assert r.severity == "WARN"
    assert r.passed is False


def test_coordinates_outside_sf_warn(sandbox):
    _load([make_row(case_location={"type": "Point", "coordinates": [-100.0, 40.0]})])

    r = _results()["coordinates_in_sf"]
    assert r.passed is False and r.observed == 1


def test_results_are_recorded(sandbox):
    _load([make_row()])
    checks.run(DAY)

    n = fetch("SELECT COUNT(*) FROM dq_results WHERE load_date=?", (DAY.isoformat(),))[0][0]
    assert n == len(checks.CHECKS)


def test_main_exit_code_reflects_hard_failure(sandbox):
    _load([make_row(rowid="f-1", received_dttm="2099-01-01T00:00:00.000")])
    assert checks.main(["--date", DAY.isoformat()]) == 1
