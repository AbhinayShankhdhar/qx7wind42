"""Download January 2026 wind data from Elexon once and save it to backend/data/.

Run from the backend folder:   python -m scripts.build_cache

Why a cache? The live download takes ~70 API calls. Shipping a snapshot makes the
deployed app fast and keeps it working even if Elexon is slow or down.
"""
import logging

from app.config import CACHE_FILE
from app.data_store import fetch_live, save_cache

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raw = fetch_live()
    save_cache(raw)
    print(f"Saved {len(raw['actuals'])} actual and {len(raw['forecasts'])} forecast points to {CACHE_FILE}")
