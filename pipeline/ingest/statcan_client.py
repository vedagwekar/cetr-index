"""
pipeline/ingest/statcan_client.py
==================================
Fetches Statistics Canada data tables via their public download API.
Handles ZIP extraction, CSV parsing, province name normalization,
retry logic, and raw file caching.

All three tables used by this project are fetched here:
  - 36-10-0402-01  GDP by industry by province
  - 14-10-0023-01  Employment by industry by province
  - 11-10-0223-01  Household spending by province

Usage
-----
  python -m pipeline.ingest.statcan_client
  # → downloads all tables to data/raw/

  from pipeline.ingest.statcan_client import fetch_table
  df = fetch_table("36-10-0402-01")

Author : Ved
Updated: 2026-05-24
"""

import io
import json
import logging
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

from pipeline.constants import (
    DATA_RAW,
    EXCLUDED_TERRITORIES,
    LOG_DATE,
    LOG_FORMAT,
    PROVINCE_MAP,
    REQUEST_BACKOFF,
    REQUEST_DELAY,
    REQUEST_RETRIES,
    REQUEST_TIMEOUT,
    STATCAN_TABLES,
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(format=LOG_FORMAT, datefmt=LOG_DATE, level=logging.INFO)
log = logging.getLogger("statcan_client")

# Stats Canada CSV download endpoint
# PID is the table number with hyphens removed
_BASE_URL = "https://www150.statcan.gc.ca/t1/tbl1/en/dtbl/downloadTbl/csvDownload?pid={pid}"


def _pid(table_id: str) -> str:
    """Convert '36-10-0402-01' → '3610040201'."""
    return table_id.replace("-", "")


def _fetch_with_retry(url: str) -> bytes:
    """
    GET a URL with exponential backoff retry logic.

    Parameters
    ----------
    url : str
        The URL to fetch.

    Returns
    -------
    bytes
        Raw response content.

    Raises
    ------
    requests.HTTPError
        If all retries are exhausted and the request still fails.
    """
    last_exc: Exception | None = None
    for attempt in range(REQUEST_RETRIES):
        try:
            log.debug("GET %s (attempt %d/%d)", url, attempt + 1, REQUEST_RETRIES)
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.content
        except requests.RequestException as e:
            last_exc = e
            wait = REQUEST_BACKOFF * (2 ** attempt)
            log.warning("Request failed (attempt %d/%d): %s — retrying in %.1fs",
                        attempt + 1, REQUEST_RETRIES, e, wait)
            time.sleep(wait)
    raise requests.HTTPError(f"All {REQUEST_RETRIES} attempts failed for {url}") from last_exc


def fetch_table(
    table_id: str,
    output_dir: Path = DATA_RAW,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Download a Statistics Canada data table and return as a DataFrame.

    The raw CSV is cached in output_dir. If it already exists and
    force_refresh is False, the cached version is returned without
    making a network request.

    Parameters
    ----------
    table_id : str
        Stats Canada table identifier, e.g. '36-10-0402-01'.
    output_dir : Path
        Directory to save/load the raw CSV.
    force_refresh : bool
        If True, re-download even if cached file exists.

    Returns
    -------
    pd.DataFrame
        Raw table data with a 'province' column (2-letter abbreviations)
        replacing the original GEO column. Territory rows are dropped.

    Notes
    -----
    Stats Canada returns a ZIP containing two CSVs:
      - {pid}.csv        : the data
      - {pid}_MetaData.csv : column metadata (not used here)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_path = output_dir / f"{table_id}_raw.csv"

    if cache_path.exists() and not force_refresh:
        log.info("Using cached %s", cache_path.name)
        df = pd.read_csv(cache_path, encoding="latin-1", low_memory=False)
        return df

    url = _BASE_URL.format(pid=_pid(table_id))
    log.info("Fetching Stats Canada table %s ...", table_id)

    content = _fetch_with_retry(url)
    time.sleep(REQUEST_DELAY)  # polite delay

    # Stats Canada always returns a ZIP
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        data_filename = f"{_pid(table_id)}.csv"
        try:
            with z.open(data_filename) as f:
                df = pd.read_csv(f, encoding="latin-1", low_memory=False)
        except KeyError:
            # Some tables use slightly different naming — find it
            csv_files = [n for n in z.namelist() if n.endswith(".csv") and "MetaData" not in n]
            if not csv_files:
                raise ValueError(f"No data CSV found in ZIP for table {table_id}. Files: {z.namelist()}")
            with z.open(csv_files[0]) as f:
                df = pd.read_csv(f, encoding="latin-1", low_memory=False)

    log.info("  Downloaded %d rows, %d columns", len(df), len(df.columns))

    # Add normalized province abbreviation column
    if "GEO" in df.columns:
        df["province"] = df["GEO"].map(PROVINCE_MAP)
        # Drop territories and national-level aggregates
        df = df[df["province"].notna()].copy()
        log.info("  After province filter: %d rows", len(df))

    # Save raw copy
    df.to_csv(cache_path, index=False)
    log.info("  Saved to %s", cache_path)

    return df


def fetch_all_tables(output_dir: Path = DATA_RAW, force_refresh: bool = False) -> dict[str, pd.DataFrame]:
    """
    Fetch all Stats Canada tables required by the CETR pipeline.

    Returns
    -------
    dict[str, pd.DataFrame]
        Keys match STATCAN_TABLES (gdp_by_industry, employment_by_industry,
        household_spending).
    """
    results = {}
    for name, table_id in STATCAN_TABLES.items():
        log.info("=== Fetching %s (%s) ===", name, table_id)
        try:
            df = fetch_table(table_id, output_dir=output_dir, force_refresh=force_refresh)
            results[name] = df
            log.info("  ✓ %s: %d rows", name, len(df))
        except Exception as e:
            log.error("  ✗ Failed to fetch %s: %s", name, e)
            results[name] = pd.DataFrame()  # empty — downstream scripts handle this

    return results


def log_ingest_result(table_id: str, rows: int, status: str, error: str = "") -> None:
    """
    Append a record to data/raw/ingest_log.json for pipeline monitoring.
    """
    log_path = DATA_RAW / "ingest_log.json"
    existing = []
    if log_path.exists():
        with open(log_path) as f:
            try:
                existing = json.load(f)
            except json.JSONDecodeError:
                existing = []

    from datetime import datetime
    existing.append({
        "timestamp": datetime.utcnow().isoformat(),
        "table_id": table_id,
        "rows_fetched": rows,
        "status": status,
        "error": error,
    })

    with open(log_path, "w") as f:
        json.dump(existing, f, indent=2)


if __name__ == "__main__":
    log.info("Starting Stats Canada ingestion...")
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    results = fetch_all_tables()
    log.info("\nSummary:")
    for name, df in results.items():
        status = "✓" if len(df) > 0 else "✗ EMPTY"
        log.info("  %s %s: %d rows", status, name, len(df))
