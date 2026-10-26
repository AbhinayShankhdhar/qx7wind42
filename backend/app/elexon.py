"""Thin client for the two Elexon BMRS stream endpoints we need.

Uses only the Python standard library so the backend has no HTTP dependency.
Each function returns clean, compact records:
  actuals:   list of (start_epoch, generation_mw)
  forecasts: list of (start_epoch, publish_epoch, generation_mw)
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

from .config import ELEXON_BASE_URL

REQUEST_TIMEOUT_S = 60
MAX_RETRIES = 3


def _get_json(path: str, params: dict) -> list[dict]:
    """GET an Elexon endpoint and return its list of records (with simple retries)."""
    url = f"{ELEXON_BASE_URL}{path}?{urllib.parse.urlencode(params)}"
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
                payload = json.load(resp)
            # Stream endpoints return a bare list; other endpoints wrap it in {"data": [...]}.
            return payload["data"] if isinstance(payload, dict) else payload
        except Exception as exc:  # network hiccups, 5xx, timeouts
            last_error = exc
            time.sleep(2 * attempt)
    raise RuntimeError(f"Elexon request failed after {MAX_RETRIES} tries: {url}") from last_error


def parse_time(value: str) -> int:
    """Elexon ISO timestamp ('2026-01-02T00:00:00Z') -> UTC epoch seconds."""
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


def _daterange(start: date, end: date, step_days: int):
    """Yield (chunk_start, chunk_end) pairs covering [start, end] inclusive."""
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=step_days - 1), end)
        yield current, chunk_end
        current = chunk_end + timedelta(days=1)


def fetch_actuals(settlement_from: date, settlement_to: date) -> list[tuple[int, float]]:
    """Actual national WIND generation (FUELHH, 30-minute resolution).

    If a period was published more than once, the latest publication wins.
    """
    latest: dict[int, tuple[int, float]] = {}  # start -> (publish, mw)
    for chunk_from, chunk_to in _daterange(settlement_from, settlement_to, step_days=7):
        rows = _get_json(
            "/datasets/FUELHH/stream",
            {
                "settlementDateFrom": chunk_from.isoformat(),
                "settlementDateTo": chunk_to.isoformat(),
                "fuelType": "WIND",
            },
        )
        for row in rows:
            if row.get("fuelType") != "WIND" or row.get("generation") is None:
                continue
            start = parse_time(row["startTime"])
            publish = parse_time(row["publishTime"]) if row.get("publishTime") else 0
            if start not in latest or publish >= latest[start][0]:
                latest[start] = (publish, float(row["generation"]))
    return sorted((start, mw) for start, (_, mw) in latest.items())


def fetch_forecasts(publish_from: datetime, publish_to: datetime) -> list[tuple[int, int, float]]:
    """Every wind forecast (WINDFOR) published in the window, all horizons."""
    seen: set[tuple[int, int]] = set()
    out: list[tuple[int, int, float]] = []
    chunk_start = publish_from
    while chunk_start < publish_to:
        chunk_end = min(chunk_start + timedelta(days=1), publish_to)
        rows = _get_json(
            "/datasets/WINDFOR/stream",
            {
                "publishDateTimeFrom": chunk_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "publishDateTimeTo": chunk_end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
        for row in rows:
            if row.get("generation") is None:
                continue
            key = (parse_time(row["startTime"]), parse_time(row["publishTime"]))
            if key in seen:  # chunk boundaries can overlap
                continue
            seen.add(key)
            out.append((key[0], key[1], float(row["generation"])))
        chunk_start = chunk_end
    out.sort()
    return out
