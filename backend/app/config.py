"""Central configuration: the business assumptions live here, in one place."""
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

# UK market days are defined in local UK time.
UK_TZ = ZoneInfo("Europe/London")

# "Purchase decisions made in January 2026" -> decisions on Jan 1 .. Jan 31,
# each one buying power for the NEXT day. So delivery days are Jan 2 .. Feb 1.
DECISION_START = date(2026, 1, 1)
DECISION_END = date(2026, 1, 31)
DELIVERY_START = date(2026, 1, 2)
DELIVERY_END = date(2026, 2, 1)  # inclusive

# Assumed time on the day before delivery (D-1) when the buy decision is made.
# Only forecasts published at or before this moment could have been used.
# The user can change it in the UI; this is just the default.
DEFAULT_CUTOFF_HOUR = 10
DEFAULT_CUTOFF_MINUTE = 0

# Forecast-horizon analysis looks at forecasts published up to this many hours ahead.
MAX_HORIZON_HOURS = 48
HORIZON_BUCKET_HOURS = 6

# Histogram bin width for forecast errors (MW).
HISTOGRAM_BIN_MW = 500

ELEXON_BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_FILE = DATA_DIR / "elexon_wind_jan2026.json"
