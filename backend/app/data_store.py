"""Loads the dataset once per process: from the local cache file if present,
otherwise live from Elexon (and then saves the cache for next time).

Cached format (compact, epoch seconds):
  {"actuals": [[start, mw], ...], "forecasts": [[start, publish, mw], ...], "fetched_at": "..."}
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from functools import lru_cache

from . import elexon
from .config import CACHE_FILE, DELIVERY_END, DELIVERY_START, MAX_HORIZON_HOURS, UK_TZ

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Dataset:
    actuals: dict[int, float]                 # start_epoch -> MW
    forecasts: list[tuple[int, int, float]]   # (start, publish, MW), sorted
    fetched_at: str
    source: str                                # "cache" or "live"


def delivery_window_utc() -> tuple[int, int]:
    """[first period start, last period end) of the delivery window, in UTC epoch seconds."""
    start = datetime.combine(DELIVERY_START, time(0), UK_TZ)
    end = datetime.combine(DELIVERY_END + timedelta(days=1), time(0), UK_TZ)
    return int(start.timestamp()), int(end.timestamp())


def _trim(actuals, forecasts):
    """Keep only rows relevant to the delivery window (keeps the cache small)."""
    lo, hi = delivery_window_utc()
    max_h = MAX_HORIZON_HOURS * 3600
    actuals = [(s, mw) for s, mw in actuals if lo <= s < hi]
    forecasts = [(s, p, mw) for s, p, mw in forecasts if lo <= s < hi and 0 <= s - p <= max_h]
    return actuals, forecasts


def fetch_live() -> dict:
    lo, hi = delivery_window_utc()
    log.info("Fetching actuals and forecasts from Elexon...")
    actuals = elexon.fetch_actuals(DELIVERY_START - timedelta(days=1), DELIVERY_END + timedelta(days=1))
    forecasts = elexon.fetch_forecasts(
        datetime.fromtimestamp(lo - MAX_HORIZON_HOURS * 3600, timezone.utc),
        datetime.fromtimestamp(hi, timezone.utc),
    )
    actuals, forecasts = _trim(actuals, forecasts)
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "actuals": [list(r) for r in actuals],
        "forecasts": [list(r) for r in forecasts],
    }


def save_cache(raw: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(raw, separators=(",", ":")))


@lru_cache(maxsize=1)
def get_dataset() -> Dataset:
    if CACHE_FILE.exists():
        raw, source = json.loads(CACHE_FILE.read_text()), "cache"
    else:
        raw, source = fetch_live(), "live"
        try:
            save_cache(raw)
        except OSError:  # read-only filesystem (e.g. serverless) - fine, keep it in memory
            log.warning("Could not write cache file; continuing with in-memory data")
    return Dataset(
        actuals={int(s): float(mw) for s, mw in raw["actuals"]},
        forecasts=sorted((int(s), int(p), float(mw)) for s, p, mw in raw["forecasts"]),
        fetched_at=raw.get("fetched_at", ""),
        source=source,
    )
