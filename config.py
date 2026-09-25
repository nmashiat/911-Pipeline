"""Single place for settings. Import from here; never hardcode elsewhere."""
from pathlib import Path

# SF Fire/EMS Dispatched Calls for Service (Socrata dataset id nuek-vuh3)
API_URL = "https://data.sf.gov/resource/nuek-vuh3.json"

# Socrata paginates; 50k rows per request is the documented safe ceiling
PAGE_SIZE = 50_000

# Column the dataset uses for "when the call came in" — we filter days on this
DATE_COLUMN = "received_dttm"

# Folders
ROOT = Path(__file__).parent
RAW_DIR = ROOT / "data" / "raw"
STAGING_DIR = ROOT / "data" / "staging"
DB_PATH = ROOT / "sf911.db"

# Identify yourself to the API. Polite, and helps if they ever need to contact you.
USER_AGENT = "sf911-pipeline (portfolio project; github.com/nmashiat)"
