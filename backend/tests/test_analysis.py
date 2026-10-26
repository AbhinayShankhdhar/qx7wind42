"""Unit tests for the analysis logic. Run from backend/:  python -m pytest -q"""
import math
from datetime import date, datetime, timezone

from app import analysis

H = 3600


def utc(y, mo, d, h=0, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp())


def test_cutoff_is_previous_day_in_uk_time():
    # January = GMT, so 10:00 UK on Jan 1 is 10:00 UTC
    assert analysis.cutoff_for_delivery_day(date(2026, 1, 2), 10, 0) == utc(2026, 1, 1, 10)
    # July = BST (UTC+1), so 10:00 UK is 09:00 UTC - daylight saving handled
    assert analysis.cutoff_for_delivery_day(date(2026, 7, 2), 10, 0) == utc(2026, 7, 1, 9)


def test_latest_forecast_before_cutoff_ignores_later_forecasts():
    start = utc(2026, 1, 2, 12)
    forecasts = [
        (start, utc(2026, 1, 1, 6), 100.0),
        (start, utc(2026, 1, 1, 9), 200.0),   # latest one allowed
        (start, utc(2026, 1, 1, 11), 999.0),  # published after the 10:00 cutoff -> not usable
    ]
    index = analysis.index_forecasts(forecasts)
    assert analysis.latest_forecast_before(index, start, utc(2026, 1, 1, 10)) == (utc(2026, 1, 1, 9), 200.0)
    # Cutoff exactly on a publish time counts as available
    assert analysis.latest_forecast_before(index, start, utc(2026, 1, 1, 11))[1] == 999.0
    # Nothing published yet
    assert analysis.latest_forecast_before(index, start, utc(2026, 1, 1, 5)) is None
    # Unknown target time
    assert analysis.latest_forecast_before(index, start + H, utc(2026, 1, 1, 10)) is None


def test_summarise_metrics():
    errors = [100.0, -100.0, 300.0, -300.0]
    actuals = [1000.0] * 4
    m = analysis.summarise(errors, actuals)
    assert m["n"] == 4
    assert m["mae"] == 200
    assert m["bias"] == 0
    assert math.isclose(m["rmse"], math.sqrt((1e4 + 1e4 + 9e4 + 9e4) / 4))
    assert m["nmae_pct"] == 20
    assert m["over_forecast_share_pct"] == 50
    assert m["max_abs"] == 300


def test_summarise_empty():
    assert analysis.summarise([], []) == {"n": 0}


def test_percentile_interpolates():
    assert analysis.percentile([1, 2, 3, 4, 5], 50) == 3
    assert analysis.percentile([0, 10], 90) == 9


def test_decision_series_end_to_end():
    day = date(2026, 1, 2)
    t1, t2 = utc(2026, 1, 2, 0), utc(2026, 1, 2, 1)
    actuals = {t1: 1000.0, t2: 2000.0}
    forecasts = [
        (t1, utc(2026, 1, 1, 8), 1100.0),
        (t1, utc(2026, 1, 1, 12), 5000.0),  # after cutoff
        (t2, utc(2026, 1, 1, 9), 1500.0),
    ]
    rows = analysis.build_decision_series(actuals, forecasts, [day], 10, 0)
    assert [r["forecast"] for r in rows] == [1100.0, 1500.0]
    assert [r["error"] for r in rows] == [100.0, -500.0]
    assert rows[0]["horizon_h"] == 16.0
    assert rows[0]["hour"] == 0


def test_periods_without_actuals_are_skipped():
    t1 = utc(2026, 1, 2, 0)
    rows = analysis.build_decision_series({}, [(t1, utc(2026, 1, 1, 8), 1.0)], [date(2026, 1, 2)], 10, 0)
    assert rows == []


def test_histogram_bins_cover_all_errors():
    rows = [{"error": e} for e in (-600, -10, 0, 499, 501)]
    hist = analysis.error_histogram(rows, bin_mw=500)
    assert sum(b["count"] for b in hist) == 5
    assert hist[0]["from"] == -1000 and hist[-1]["to"] == 1000


def test_accuracy_by_horizon_buckets():
    start = utc(2026, 1, 2, 12)
    actuals = {start: 1000.0}
    forecasts = [
        (start, start - 2 * H, 1100.0),   # 2h ahead  -> bucket 0-6
        (start, start - 30 * H, 1500.0),  # 30h ahead -> bucket 30-36
        (start, start - 60 * H, 9999.0),  # beyond 48h -> ignored
    ]
    out = analysis.accuracy_by_horizon(actuals, forecasts, (start - H, start + H), bucket_h=6, max_h=48)
    assert len(out) == 8
    assert out[0]["mae"] == 100 and out[0]["n"] == 1
    assert out[5]["mae"] == 500
    assert sum(b["n"] for b in out) == 2
