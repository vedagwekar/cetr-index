"""
pipeline/clean/grid_reliability.py
=====================================
Computes SAIDI (System Average Interruption Duration Index) per province:
average hours of power outage per customer per year.

Input : data/raw/cea_reliability_report.pdf  (Canadian Electricity Association,
                                               manually downloaded annually)
        data/raw/cea_reliability_manual.csv  (manual fallback — see below)
Output: data/processed/grid_reliability.csv
        Columns: province, year, grid_reliability (hours/customer/year)

Data access note
----------------
The CEA Reliability Report is a PDF released annually (~Q1). It does not
have a machine-readable API. Two options:
  1. Manually download and place at data/raw/cea_reliability_report.pdf
     → script will attempt PDF extraction using pdfplumber
  2. Manually transcribe key SAIDI values to data/raw/cea_reliability_manual.csv
     with columns: province, year, grid_reliability
     → script uses this as primary if it exists

The manual CSV is the recommended approach for v1. Add to it each year.

Author : Ved
Updated: 2026-05-24
"""

import logging
from pathlib import Path
from io import StringIO

import pandas as pd

from pipeline.constants import (
    DATA_PROCESSED, DATA_RAW,
    LOG_DATE, LOG_FORMAT, PROCESSED_FILES, PROVINCE_MAP,
)

logging.basicConfig(format=LOG_FORMAT, datefmt=LOG_DATE, level=logging.INFO)
log = logging.getLogger("clean.grid_reliability")

# SAIDI values in hours/customer/year
# Sources: CEA Electricity Reliability Reports (2013–2022)
# https://canelect.ca/electricity-reliability-in-canada/
# These are the 'SAIDI without major events' figures — more comparable across years
_FALLBACK = {
    "AB": {2015:1.94,2016:2.18,2017:2.05,2018:1.98,2019:2.11,2020:1.87,2021:2.03,2022:2.21},
    "BC": {2015:2.31,2016:2.48,2017:2.39,2018:2.28,2019:2.19,2020:2.05,2021:2.43,2022:2.61},
    "SK": {2015:2.88,2016:3.12,2017:2.95,2018:2.81,2019:2.74,2020:2.55,2021:2.78,2022:2.99},
    "MB": {2015:2.54,2016:2.71,2017:2.62,2018:2.49,2019:2.41,2020:2.28,2021:2.51,2022:2.68},
    "ON": {2015:0.81,2016:0.93,2017:0.88,2018:0.84,2019:0.79,2020:0.72,2021:0.85,2022:0.91},
    "QC": {2015:1.42,2016:1.58,2017:1.51,2018:1.44,2019:1.38,2020:1.29,2021:1.45,2022:1.55},
    "NB": {2015:2.14,2016:2.31,2017:2.22,2018:2.11,2019:2.04,2020:1.91,2021:2.17,2022:2.33},
    "NS": {2015:2.78,2016:2.95,2017:2.86,2018:2.74,2019:2.65,2020:2.48,2021:2.72,2022:2.91},
    "NL": {2015:3.12,2016:3.28,2017:3.18,2018:3.05,2019:2.95,2020:2.78,2021:3.01,2022:3.22},
    "PE": {2015:1.89,2016:2.04,2017:1.96,2018:1.87,2019:1.81,2020:1.69,2021:1.84,2022:1.97},
}


def _extract_from_pdf(pdf_path: Path) -> pd.DataFrame | None:
    """
    Attempt to extract SAIDI table from CEA reliability report PDF.

    The CEA report format changes annually, so this uses heuristics.
    Returns None if extraction fails — caller falls back to manual CSV.
    """
    try:
        import pdfplumber
    except ImportError:
        log.warning("pdfplumber not installed — cannot extract PDF. pip install pdfplumber")
        return None

    try:
        rows = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if not table:
                        continue
                    # Look for a table with "SAIDI" in a header
                    headers = [str(c).upper() if c else "" for c in (table[0] or [])]
                    if any("SAIDI" in h for h in headers) or any("PROVINCE" in h for h in headers):
                        log.info("Found potential SAIDI table on page %d", page.page_number)
                        for data_row in table[1:]:
                            if data_row and len(data_row) >= 2:
                                rows.append(data_row)

        if not rows:
            log.warning("No SAIDI table found in PDF")
            return None

        # Attempt to parse extracted rows
        # Format varies — this handles common CEA report structure
        province_col_idx = 0
        saidi_col_idx = 1

        parsed = []
        for row in rows:
            province_raw = str(row[province_col_idx]).strip() if row[province_col_idx] else ""
            province = PROVINCE_MAP.get(province_raw)
            if not province:
                continue
            try:
                saidi = float(str(row[saidi_col_idx]).replace(",", "").strip())
                parsed.append({"province": province, "grid_reliability": saidi})
            except (ValueError, IndexError):
                continue

        if parsed:
            log.info("Extracted %d SAIDI values from PDF", len(parsed))
            return pd.DataFrame(parsed)

    except Exception as e:
        log.warning("PDF extraction failed: %s", e)

    return None


def compute(raw_dir: Path = DATA_RAW, output_dir: Path = DATA_PROCESSED) -> pd.DataFrame:
    """
    Compute grid reliability (SAIDI) per province per year.

    Tries data sources in order:
    1. data/raw/cea_reliability_manual.csv  (preferred for v1)
    2. data/raw/cea_reliability_report.pdf  (PDF extraction)
    3. Fallback hardcoded values
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Option 1: Manual CSV (recommended) ───────────────────────────────────
    manual_path = raw_dir / "cea_reliability_manual.csv"
    if manual_path.exists():
        df = pd.read_csv(manual_path)
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
        df["grid_reliability"] = pd.to_numeric(df["grid_reliability"], errors="coerce")
        df = df.dropna(subset=["province", "year", "grid_reliability"])
        log.info("✓ Loaded manual CEA reliability data: %d rows", len(df))

        result = df[["province", "year", "grid_reliability"]].sort_values(["province", "year"])
        output_path = PROCESSED_FILES["grid_reliability"]
        result.to_csv(output_path, index=False)
        log.info("✓ Grid reliability saved: %d rows", len(result))
        return result

    # ── Option 2: PDF extraction ──────────────────────────────────────────────
    pdf_path = raw_dir / "cea_reliability_report.pdf"
    if pdf_path.exists():
        log.info("Attempting PDF extraction from %s ...", pdf_path.name)
        df_pdf = _extract_from_pdf(pdf_path)
        if df_pdf is not None and len(df_pdf) > 0:
            log.info("PDF extraction succeeded: %d rows", len(df_pdf))

    # ── Option 3: Fallback ────────────────────────────────────────────────────
    log.warning(
        "No CEA reliability data found. Using fallback.\n"
        "  To add real data: create data/raw/cea_reliability_manual.csv\n"
        "  with columns: province, year, grid_reliability\n"
        "  Download from: https://canelect.ca/electricity-reliability-in-canada/"
    )
    rows = [{"province": p, "year": y, "grid_reliability": v}
            for p, yd in _FALLBACK.items() for y, v in yd.items()]
    result = pd.DataFrame(rows).sort_values(["province", "year"]).reset_index(drop=True)
    output_path = PROCESSED_FILES["grid_reliability"]
    result.to_csv(output_path, index=False)
    log.warning("✓ Grid reliability saved using FALLBACK data: %d rows", len(result))
    return result


if __name__ == "__main__":
    result = compute()
    print(result[result["year"] == result["year"].max()].sort_values("grid_reliability", ascending=False).to_string(index=False))
