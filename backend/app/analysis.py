"""Core business logic. Pure Python, no I/O, so it is easy to unit-test.

Key idea: for every 30-min/hourly period on delivery day D, the trading team
could only have used a forecast that was PUBLISHED before their decision
cutoff on D-1. We pick the latest such forecast ("decision forecast") and
compare it with what the wind farms actually generated.

Error convention: error = forecast - actual
  error > 0  -> forecast was too optimistic (less wind came than expected -> shortfall risk)
  error < 0  -> forecast was too pessimistic (more wind came -> surplus bought)
"""
from __future__ import annotations

import math
from bisect import bisect_right
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from .config import HISTOGRAM_BIN_MW, HORIZON_BUCKET_HOURS, MAX_HORIZON_HOURS, UK_TZ


# ---------------------------------------------------------------- helpers
def percentile(values: list[float], q: float) -> float:
    """Linear-interpolated percentile, q in [0, 100]."""
    if not values:
        return float("nan")
    s = sorted(values)
    k = (len(s) - 1) * q / 100
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def cutoff_for_delivery_day(day: date, hour: int, minute: int) -> int:
    """Decision moment (UTC epoch) = hour:minute UK time on the day before `day`."""
    return int(datetime.combine(day - timedelta(days=1), time(hour, minute), UK_TZ).timestamp())


def uk_local(epoch: int) -> datetime:
    return datetime.fromtimestamp(epoch, timezone.utc).astimezone(UK_TZ)


def index_forecasts(forecasts: list[tuple[int, int, float]]) -> dict[int, tuple[list[int], list[float]]]:
    """start -> (sorted publish times, matching MW values) for fast 'latest before' lookups."""
    grouped: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for start, publish, mw in forecasts:
        grouped[start].append((publish, mw))
    index = {}
    for start, rows in grouped.items():
        rows.sort()
        index[start] = ([p for p, _ in rows], [mw for _, mw in rows])
    return index


def latest_forecast_before(index, start: int, cutoff: int) -> tuple[int, float] | None:
    """Latest forecast for `start` with publish time <= cutoff, or None."""
    if start not in index:
        return None
    publishes, values = index[start]
    i = bisect_right(publishes, cutoff) - 1
    return (publishes[i], values[i]) if i >= 0 else None


def summarise(errors: list[float], actual_values: list[float]) -> dict:
    """Headline accuracy metrics for a set of (forecast - actual) errors."""
    n = len(errors)
    if n == 0:
        return {"n": 0}
    abs_err = [abs(e) for e in errors]
    mean_actual = sum(actual_values) / n
    return {
        "n": n,
        "mae": sum(abs_err) / n,                                  # average size of the miss
        "rmse": math.sqrt(sum(e * e for e in errors) / n),        # punishes big misses
        "bias": sum(errors) / n,                                  # + = over-forecasts on average
        "nmae_pct": 100 * sum(abs_err) / n / mean_actual if mean_actual else None,
        "p50_abs": percentile(abs_err, 50),
        "p90_abs": percentile(abs_err, 90),
        "p95_abs": percentile(abs_err, 95),
        "max_abs": max(abs_err),
        # Safety buffer: in 90% / 95% of periods the shortfall (forecast above actual)
        # was no bigger than this. Directly usable as a procurement margin.
        "shortfall_p90": max(0.0, percentile(errors, 90)),
        "shortfall_p95": max(0.0, percentile(errors, 95)),
        "over_forecast_share_pct": 100 * sum(1 for e in errors if e > 0) / n,
        "mean_actual": mean_actual,
    }


# ---------------------------------------------------------------- main analysis
def build_decision_series(actuals: dict[int, float], forecasts, days: list[date],
                          cutoff_hour: int, cutoff_minute: int) -> list[dict]:
    """One row per target period that has both an actual and a decision-time forecast."""
    index = index_forecasts(forecasts)
    rows = []
    for day in days:
        cutoff = cutoff_for_delivery_day(day, cutoff_hour, cutoff_minute)
        day_start = int(datetime.combine(day, time(0), UK_TZ).timestamp())
        day_end = int(datetime.combine(day + timedelta(days=1), time(0), UK_TZ).timestamp())
        for start in sorted(s for s in index if day_start <= s < day_end):
            found = latest_forecast_before(index, start, cutoff)
            if found is None or start not in actuals:
                continue
            publish, forecast_mw = found
            actual_mw = actuals[start]
            rows.append({
                "start": start,
                "day": day.isoformat(),
                "hour": uk_local(start).hour,
                "publish": publish,
                "horizon_h": round((start - publish) / 3600, 2),
                "forecast": forecast_mw,
                "actual": actual_mw,
                "error": forecast_mw - actual_mw,
            })
    return rows


def error_by_hour(rows) -> list[dict]:
    buckets = defaultdict(list)
    for r in rows:
        buckets[r["hour"]].append(r)
    out = []
    for hour in range(24):
        rs = buckets.get(hour, [])
        errs = [r["error"] for r in rs]
        out.append({
            "hour": hour,
            "n": len(rs),
            "mae": sum(abs(e) for e in errs) / len(errs) if errs else None,
            "bias": sum(errs) / len(errs) if errs else None,
        })
    return out


def daily_summary(rows) -> list[dict]:
    buckets = defaultdict(list)
    for r in rows:
        buckets[r["day"]].append(r)
    out = []
    for day in sorted(buckets):
        rs = buckets[day]
        errs = [r["error"] for r in rs]
        out.append({
            "day": day,
            "n": len(rs),
            "mae": sum(abs(e) for e in errs) / len(errs),
            "bias": sum(errs) / len(errs),
            "actual_mwh": sum(r["actual"] for r in rs),   # summed MW over periods, for ranking only
            "forecast_mwh": sum(r["forecast"] for r in rs),
        })
    return out


def error_histogram(rows, bin_mw: int = HISTOGRAM_BIN_MW) -> list[dict]:
    if not rows:
        return []
    counts = defaultdict(int)
    for r in rows:
        counts[math.floor(r["error"] / bin_mw)] += 1
    lo, hi = min(counts), max(counts)
    return [{"from": b * bin_mw, "to": (b + 1) * bin_mw, "count": counts.get(b, 0)} for b in range(lo, hi + 1)]


def accuracy_by_horizon(actuals: dict[int, float], forecasts, window: tuple[int, int],
                        bucket_h: int = HORIZON_BUCKET_HOURS,
                        max_h: int = MAX_HORIZON_HOURS) -> list[dict]:
    """How does accuracy change the further ahead the forecast was made? Uses ALL forecasts."""
    lo, hi = window
    errs_by_bucket = defaultdict(list)
    for start, publish, mw in forecasts:
        if not (lo <= start < hi) or start not in actuals:
            continue
        horizon = (start - publish) / 3600
        if 0 <= horizon < max_h:
            errs_by_bucket[int(horizon // bucket_h)].append(mw - actuals[start])
    out = []
    for b in range(max_h // bucket_h):
        errs = errs_by_bucket.get(b, [])
        out.append({
            "from_h": b * bucket_h,
            "to_h": (b + 1) * bucket_h,
            "n": len(errs),
            "mae": sum(abs(e) for e in errs) / len(errs) if errs else None,
            "bias": sum(errs) / len(errs) if errs else None,
        })
    return out


def run_analysis(actuals, forecasts, days: list[date], cutoff_hour: int, cutoff_minute: int) -> dict:
    rows = build_decision_series(actuals, forecasts, days, cutoff_hour, cutoff_minute)
    window = (
        int(datetime.combine(days[0], time(0), UK_TZ).timestamp()),
        int(datetime.combine(days[-1] + timedelta(days=1), time(0), UK_TZ).timestamp()),
    )
    # Actuals for the chart, even where no forecast exists (e.g. 30-min actuals vs hourly forecasts).
    actual_series = [{"start": s, "actual": mw} for s, mw in sorted(actuals.items()) if window[0] <= s < window[1]]
    return {
        "series": rows,
        "actual_series": actual_series,
        "metrics": summarise([r["error"] for r in rows], [r["actual"] for r in rows]),
        "by_hour": error_by_hour(rows),
        "daily": daily_summary(rows),
        "histogram": error_histogram(rows),
        "by_horizon": accuracy_by_horizon(actuals, forecasts, window),
    }
