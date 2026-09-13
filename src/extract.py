"""
Step 1 — Extract one day of raw data from the SF API and save it untouched.

Run:
    python -m src.extract --date 2026-09-01

Rules this file follows (these are the habits recruiters look for):
  1. Raw data is saved exactly as received. No cleaning here.
  2. One file per day, named by date, so a rerun overwrites the same file (idempotent).
  3. The API is paged; we loop until a page comes back short.
  4. We log what we did so a failure is diagnosable later.
"""
import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta

import requests

import config

log = logging.getLogger("extract")


def fetch_day(day: date) -> list[dict]:
    """Return every row whose received_dttm falls on `day`, following pagination."""
    start = datetime.combine(day, datetime.min.time()).isoformat()
    end = datetime.combine(day + timedelta(days=1), datetime.min.time()).isoformat()

    rows: list[dict] = []
    offset = 0
    session = requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT

    while True:
        params = {
            "$where": f"{config.DATE_COLUMN} >= '{start}' AND {config.DATE_COLUMN} < '{end}'",
            "$limit": config.PAGE_SIZE,
            "$offset": offset,
            "$order": ":id",  # stable ordering so paging doesn't skip/duplicate rows
        }
        log.info("requesting offset=%d", offset)
        resp = session.get(config.API_URL, params=params, timeout=60)
        resp.raise_for_status()
        page = resp.json()
        rows.extend(page)
        log.info("got %d rows (total %d)", len(page), len(rows))

        if len(page) < config.PAGE_SIZE:
            break
        offset += config.PAGE_SIZE

    return rows


def save_raw(day: date, rows: list[dict]) -> None:
    """Write the raw JSON for the day. Overwrites if it already exists."""
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = config.RAW_DIR / f"{day.isoformat()}.json"
    with path.open("w") as f:
        json.dump(rows, f)
    log.info("saved %d rows -> %s", len(rows), path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Pull one day of SF Fire/EMS calls.")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args(argv)

    day = date.fromisoformat(args.date)
    rows = fetch_day(day)

    if not rows:
        # Zero rows is suspicious for a big city. Don't fail yet — Step 3 will decide —
        # but say so loudly.
        log.warning("API returned 0 rows for %s. Check the date or the API.", day)

    save_raw(day, rows)

    # Quick look so you learn the shape of the data
    if rows:
        print("\nColumns:", sorted(rows[0].keys()))
        print("\nFirst row:", json.dumps(rows[0], indent=2))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    sys.exit(main())
