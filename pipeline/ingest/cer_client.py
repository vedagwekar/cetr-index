"""
pipeline/ingest/cer_client.py
==============================
Fetches electricity generation and capacity data from the Canada Energy
Regulator (CER) open data endpoints. Also handles the ECCC GHG inventory
download for the carbon intensity calculation.

CER endpoints are direct CSV downloads — no API key, no ZIP, just a URL.
ECCC GHG inventory is an annual ZIP containing an Excel workbook.

Usage
-----
  python -m pipeline.ingest.cer_client
  # → downloads to data/raw/

  from pipeline.ingest.cer_client import fetch_cer_generation
  df = fetch_cer_generation()

Author : Ved
Updated: 2026-05-24
"""

import io
import logging
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

from pipeline.constants import (
    CER_ENDPOINTS,
    DATA_RAW,
    LOG_DATE,
    LOG_FORMAT,
    PROVINCE_MAP,
    REQUEST_BACKOFF,
    REQUEST_DELAY,
    REQUEST_RETRIES,
    REQUEST_TIMEOUT,
)

logging.basicConfig(format=LOG_FORMAT, datefmt=LOG_DATE, level=logging.INFO)
log = logging.getLogger("cer_client")

# ECCC GHG National Inventory Report — ZIP containing Excel workbook
# Updated annually in April. ~18 month lag (2024 data → April 2026)
ECCC_GHG_URL = (
    "https://publications.gc.ca/collections/collection_2024/eccc/En81-4-2024-eng.zip"
)


def _fetch_with_retry(url: str) -> bytes:
    """GET with exponential backoff — same pattern as statcan_client."""
    last_exc: Exception | None = None
    for attempt in range(REQUEST_RETRIES):
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.content
        except requests.RequestException as e:
            last_exc = e
            wait = REQUEST_BACKOFF * (2 ** attempt)
            log.warning("Attempt %d/%d failed: %s — retry in %.1fs",
                        attempt + 1, REQUEST_RETRIES, e, wait)
            time.sleep(wait)
    raise requests.HTTPError(f"All retries exhausted for {url}") from last_exc


def fetch_cer_generation(
    output_dir: Path = DATA_RAW,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Download CER electricity generation dataset.

    Returns a DataFrame with columns:
      province (str), year (int), fuel_type (str), generation_gwh (float)

    The CER CSV includes all provinces, all years since 2005, broken down
    by fuel type (hydro, nuclear, wind, solar, natural gas, coal, etc.).
    We aggregate to total generation per province per year for carbon
    intensity calculation.

    Parameters
    ----------
    output_dir : Path
        Directory to cache the raw CSV.
    force_refresh : bool
        Re-download even if cached file exists.

    Returns
    -------
    pd.DataFrame
        Columns: province, year, fuel_type, generation_gwh
    """
    cache_path = output_dir / "cer_electricity_generation_raw.csv"

    if cache_path.exists() and not force_refresh:
        log.info("Using cached CER generation data")
        return pd.read_csv(cache_path, low_memory=False)

    url = CER_ENDPOINTS["electricity_generation"]
    log.info("Fetching CER electricity generation from %s ...", url)

    content = _fetch_with_retry(url)
    time.sleep(REQUEST_DELAY)

    df = pd.read_csv(io.BytesIO(content), encoding="latin-1", low_memory=False)
    log.info("  Raw: %d rows, %d columns", len(df), len(df.columns))
    log.info("  Columns: %s", list(df.columns))

    # CER column names vary slightly by year — normalize common patterns
    col_map = {}
    for col in df.columns:
        cl = col.lower().strip()
        if "province" in cl or cl == "geo":
            col_map[col] = "geo_raw"
        elif "year" in cl or "date" in cl or cl == "ref_date":
            col_map[col] = "year_raw"
        elif "source" in cl or "fuel" in cl or "type" in cl:
            col_map[col] = "fuel_type"
        elif "value" in cl or "generation" in cl or "gwh" in cl or "twh" in cl:
            col_map[col] = "value_raw"
        elif "unit" in cl:
            col_map[col] = "unit"
    df = df.rename(columns=col_map)

    # Normalize province to abbreviations
    if "geo_raw" in df.columns:
        df["province"] = df["geo_raw"].str.strip().map(PROVINCE_MAP)
        df = df[df["province"].notna()].copy()

    # Parse year (may be "2022" or "2022-01-01")
    if "year_raw" in df.columns:
        df["year"] = pd.to_datetime(df["year_raw"], errors="coerce").dt.year.fillna(
            pd.to_numeric(df["year_raw"], errors="coerce")
        ).astype("Int64")

    # Normalize value
    if "value_raw" in df.columns:
        df["generation_gwh"] = pd.to_numeric(df["value_raw"], errors="coerce")

    # Unit conversion: some CER files report in TWh → convert to GWh
    if "unit" in df.columns:
        twh_mask = df["unit"].str.upper().str.contains("TWH", na=False)
        df.loc[twh_mask, "generation_gwh"] *= 1000

    result_cols = ["province", "year", "fuel_type", "generation_gwh"]
    available = [c for c in result_cols if c in df.columns]
    result = df[available].dropna(subset=["province", "year"]).copy()

    result.to_csv(cache_path, index=False)
    log.info("  Saved %d rows to %s", len(result), cache_path.name)

    return result


def fetch_cer_generation_totals(
    output_dir: Path = DATA_RAW,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Return total electricity generation per province per year (all fuel types summed).

    This is what carbon_intensity.py needs:
      province | year | total_generation_gwh

    Parameters
    ----------
    output_dir : Path
    force_refresh : bool

    Returns
    -------
    pd.DataFrame
        Columns: province (str), year (int), total_generation_gwh (float)
    """
    df = fetch_cer_generation(output_dir=output_dir, force_refresh=force_refresh)

    if "generation_gwh" not in df.columns:
        log.error("generation_gwh column missing from CER data — check column mapping")
        return pd.DataFrame(columns=["province", "year", "total_generation_gwh"])

    totals = (
        df.groupby(["province", "year"], as_index=False)["generation_gwh"]
        .sum()
        .rename(columns={"generation_gwh": "total_generation_gwh"})
    )

    cache_path = output_dir / "cer_generation_totals.csv"
    totals.to_csv(cache_path, index=False)
    log.info("CER generation totals: %d province-years", len(totals))

    return totals


def check_eccc_manual_download(output_dir: Path = DATA_RAW) -> bool:
    """
    Check whether the ECCC GHG inventory file has been manually placed
    in the raw data directory.

    The ECCC GHG inventory (Annex 13) is updated annually in April and
    requires manual download — the URL changes every year when a new
    edition is released. Instructions:

      1. Go to: https://www.canada.ca/en/environment-climate-change/
                services/climate-change/greenhouse-gas-emissions/inventory.html
      2. Download "National Inventory Report" → "Annex tables" ZIP
      3. Extract and place the Excel file at:
         data/raw/eccc_ghg_annex13.xlsx

    Returns
    -------
    bool
        True if the file exists, False with instructions printed if not.
    """
    expected = output_dir / "eccc_ghg_annex13.xlsx"
    if expected.exists():
        log.info("✓ ECCC GHG inventory found at %s", expected)
        return True
    else:
        log.warning(
            "✗ ECCC GHG inventory NOT FOUND at %s\n"
            "  This file must be downloaded manually (URL changes annually).\n"
            "  Instructions:\n"
            "  1. Visit: https://www.canada.ca/en/environment-climate-change/\n"
            "             services/climate-change/greenhouse-gas-emissions/inventory.html\n"
            "  2. Download 'National Inventory Report' → 'Annex tables' ZIP\n"
            "  3. Extract and save the Annex 13 Excel as: %s",
            expected, expected
        )
        return False


def fetch_all(output_dir: Path = DATA_RAW, force_refresh: bool = False) -> dict:
    """Run all CER ingestion. Returns dict of DataFrames."""
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    log.info("=== Fetching CER electricity generation ===")
    results["cer_generation"] = fetch_cer_generation(output_dir, force_refresh)
    results["cer_generation_totals"] = fetch_cer_generation_totals(output_dir, force_refresh)

    log.info("=== Checking ECCC GHG inventory ===")
    results["eccc_available"] = check_eccc_manual_download(output_dir)

    return results


if __name__ == "__main__":
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    results = fetch_all()
    log.info("\nCER ingestion complete:")
    for k, v in results.items():
        if isinstance(v, pd.DataFrame):
            log.info("  %s: %d rows", k, len(v))
        else:
            log.info("  %s: %s", k, v)
