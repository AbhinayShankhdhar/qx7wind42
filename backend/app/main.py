"""HTTP layer: validates query parameters and returns analysis results as JSON.

All business logic lives in analysis.py; this file only wires things together.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import analysis
from .config import (
    DECISION_END, DECISION_START, DEFAULT_CUTOFF_HOUR, DEFAULT_CUTOFF_MINUTE,
    DELIVERY_END, DELIVERY_START, MAX_HORIZON_HOURS,
)
from .data_store import get_dataset

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Wind Forecast Insight API", version="1.0.0")

# The React dev server runs on another port locally; allow it to call the API.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/meta")
def meta():
    ds = get_dataset()
    return {
        "decision_window": [DECISION_START.isoformat(), DECISION_END.isoformat()],
        "delivery_window": [DELIVERY_START.isoformat(), DELIVERY_END.isoformat()],
        "default_cutoff": {"hour": DEFAULT_CUTOFF_HOUR, "minute": DEFAULT_CUTOFF_MINUTE},
        "max_horizon_hours": MAX_HORIZON_HOURS,
        "data": {
            "source": ds.source,
            "fetched_at": ds.fetched_at,
            "actual_points": len(ds.actuals),
            "forecast_points": len(ds.forecasts),
        },
    }


@app.get("/api/analysis")
def get_analysis(
    start: date = Query(DELIVERY_START, description="First delivery day (UK)"),
    end: date = Query(DELIVERY_END, description="Last delivery day (UK), inclusive"),
    cutoff_hour: int = Query(DEFAULT_CUTOFF_HOUR, ge=0, le=23, description="Decision time on D-1, UK hour"),
    cutoff_minute: int = Query(DEFAULT_CUTOFF_MINUTE, ge=0, le=59),
):
    if start > end:
        raise HTTPException(400, "start must be on or before end")
    if start < DELIVERY_START or end > DELIVERY_END:
        raise HTTPException(400, f"Dates must be within {DELIVERY_START} .. {DELIVERY_END}")

    ds = get_dataset()
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    result = analysis.run_analysis(ds.actuals, ds.forecasts, days, cutoff_hour, cutoff_minute)
    result["params"] = {
        "start": start.isoformat(), "end": end.isoformat(),
        "cutoff_hour": cutoff_hour, "cutoff_minute": cutoff_minute,
    }
    return result
