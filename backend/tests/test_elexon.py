"""Tests for the Elexon client's parsing, with the network call replaced by fake data."""
from datetime import date, datetime, timezone

from app import elexon


def test_fetch_actuals_keeps_wind_and_latest_publication(monkeypatch):
    def fake_get(path, params):
        assert path == "/datasets/FUELHH/stream"
        return [
            {"startTime": "2026-01-02T00:00:00Z", "publishTime": "2026-01-02T00:30:00Z", "fuelType": "WIND", "generation": 100},
            {"startTime": "2026-01-02T00:00:00Z", "publishTime": "2026-01-02T01:00:00Z", "fuelType": "WIND", "generation": 120},
            {"startTime": "2026-01-02T00:00:00Z", "publishTime": "2026-01-02T00:30:00Z", "fuelType": "CCGT", "generation": 9000},
        ]

    monkeypatch.setattr(elexon, "_get_json", fake_get)
    rows = elexon.fetch_actuals(date(2026, 1, 2), date(2026, 1, 2))
    assert rows == [(elexon.parse_time("2026-01-02T00:00:00Z"), 120.0)]


def test_fetch_forecasts_chunks_by_day_and_dedupes(monkeypatch):
    calls = []

    def fake_get(path, params):
        calls.append(params)
        # Same row returned by every chunk: must appear only once in the output
        return [{"startTime": "2026-01-02T12:00:00Z", "publishTime": "2026-01-01T09:00:00Z", "generation": 5000}]

    monkeypatch.setattr(elexon, "_get_json", fake_get)
    out = elexon.fetch_forecasts(datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 4, tzinfo=timezone.utc))
    assert len(calls) == 3
    assert calls[0]["publishDateTimeFrom"] == "2026-01-01T00:00:00Z"
    assert len(out) == 1 and out[0][2] == 5000.0
