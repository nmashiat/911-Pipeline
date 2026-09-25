"""
Orchestrator — runs every step for one day, in order, and stops at the first failure.

    python run_pipeline.py --date 2026-09-01
    python run_pipeline.py --date 2026-09-01 --skip-extract      # reuse raw file
    python run_pipeline.py --start 2026-09-01 --end 2026-09-07   # backfill a range

Exit code 0 = all steps passed. 1 = a quality gate or reconciliation failed.
This is what an Airflow DAG will replace later; the steps themselves don't change.
"""
import argparse
import logging
import sys
from datetime import date, timedelta

from src import extract, load, checks, transform, reconcile, aggregate

log = logging.getLogger("pipeline")


def run_day(day: date, skip_extract: bool = False) -> bool:
    d = day.isoformat()
    log.info("=== %s ===", d)
    if not skip_extract:
        extract.save_raw(day, extract.fetch_day(day))
    load.main(["--date", d])

    if checks.main(["--date", d]) != 0:
        log.error("%s: quality gate failed — stopping before transform", d)
        return False

    transform.main(["--date", d])
    ok = reconcile.main(["--date", d]) == 0
    aggregate.main(["--date", d])
    if not ok:
        log.error("%s: reconciliation mismatch — data is loaded but flagged", d)
    return ok


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--date")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--skip-extract", action="store_true")
    a = p.parse_args()

    if a.date:
        days = [date.fromisoformat(a.date)]
    elif a.start and a.end:
        s, e = date.fromisoformat(a.start), date.fromisoformat(a.end)
        days = [s + timedelta(i) for i in range((e - s).days + 1)]
    else:
        p.error("give --date or --start and --end")

    results = {d.isoformat(): run_day(d, a.skip_extract) for d in days}
    failed = [d for d, ok in results.items() if not ok]
    print("\nPipeline summary:", f"{len(days)-len(failed)} ok, {len(failed)} failed", failed or "")
    return 1 if failed else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    sys.exit(main())
