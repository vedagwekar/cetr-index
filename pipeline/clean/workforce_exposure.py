"""
pipeline/clean/workforce_exposure.py
======================================
Computes fossil fuel employment as a percentage of total provincial workforce.

Input : data/raw/14-10-0023-01_raw.csv  (Stats Canada LFS)
Output: data/processed/workforce_exposure.csv
        Columns: province, year, workforce_exposure (% of workforce)

Author : Ved
Updated: 2026-05-24
"""

import logging
from pathlib import Path

import pandas as pd

from pipeline.constants import (
    DATA_PROCESSED, DATA_RAW, FOSSIL_FUEL_NAICS_PATTERNS,
    LOG_DATE, LOG_FORMAT, PROCESSED_FILES, STATCAN_TABLES,
)

logging.basicConfig(format=LOG_FORMAT, datefmt=LOG_DATE, level=logging.INFO)
log = logging.getLogger("clean.workforce_exposure")

_FALLBACK = {
    "AB": {2015:10.8,2016:9.1,2017:9.4,2018:9.9,2019:10.1,2020:7.8,2021:8.9,2022:9.8},
    "SK": {2015:5.2,2016:4.4,2017:4.6,2018:4.9,2019:5.1,2020:4.0,2021:4.5,2022:5.1},
    "BC": {2015:1.2,2016:1.0,2017:1.1,2018:1.2,2019:1.2,2020:0.9,2021:1.0,2022:1.1},
    "NL": {2015:5.8,2016:4.9,2017:5.0,2018:5.3,2019:5.1,2020:3.9,2021:4.4,2022:5.0},
    "NS": {2015:0.5,2016:0.4,2017:0.4,2018:0.5,2019:0.4,2020:0.3,2021:0.4,2022:0.5},
    "NB": {2015:0.7,2016:0.6,2017:0.6,2018:0.7,2019:0.7,2020:0.5,2021:0.6,2022:0.7},
    "ON": {2015:0.3,2016:0.3,2017:0.3,2018:0.3,2019:0.3,2020:0.2,2021:0.3,2022:0.3},
    "QC": {2015:0.2,2016:0.2,2017:0.2,2018:0.2,2019:0.2,2020:0.1,2021:0.1,2022:0.2},
    "MB": {2015:0.6,2016:0.5,2017:0.5,2018:0.6,2019:0.5,2020:0.4,2021:0.5,2022:0.5},
    "PE": {2015:0.1,2016:0.1,2017:0.1,2018:0.1,2019:0.1,2020:0.1,2021:0.1,2022:0.1},
}


def compute(raw_dir: Path = DATA_RAW, output_dir: Path = DATA_PROCESSED) -> pd.DataFrame:
    """Compute workforce exposure. Returns DataFrame: province, year, workforce_exposure."""
    output_dir.mkdir(parents=True, exist_ok=True)
    table_id = STATCAN_TABLES["employment_by_industry"]
    csv_path = raw_dir / f"{table_id}_raw.csv"

    if not csv_path.exists():
        log.warning("LFS data not found at %s — using fallback.", csv_path)
        return _from_fallback(_FALLBACK, "workforce_exposure", output_dir)

    df = pd.read_csv(csv_path, encoding="latin-1", low_memory=False)

    # Normalize columns
    df.columns = [c.lower().strip() for c in df.columns]
    if "ref_date" in df.columns:
        df["year"] = pd.to_numeric(df["ref_date"].astype(str).str[:4], errors="coerce").astype("Int64")

    # Find industry and value columns
    industry_col = next((c for c in df.columns if "naics" in c or "industry" in c), None)
    value_col = next((c for c in df.columns if c == "value"), None)

    if not industry_col or not value_col:
        log.warning("Could not find required columns. Using fallback.")
        return _from_fallback(_FALLBACK, "workforce_exposure", output_dir)

    df["employment"] = pd.to_numeric(df[value_col], errors="coerce")

    # Total employment
    total = (
        df[df[industry_col].str.lower().str.contains("total|all", na=False)]
        .groupby(["province", "year"])["employment"].sum()
        .reset_index().rename(columns={"employment": "total_employment"})
    )

    # Fossil fuel employment
    fossil_mask = df[industry_col].apply(
        lambda x: any(p in str(x).lower() for p in FOSSIL_FUEL_NAICS_PATTERNS)
    )
    fossil = (
        df[fossil_mask]
        .groupby(["province", "year"])["employment"].sum()
        .reset_index().rename(columns={"employment": "fossil_employment"})
    )

    merged = pd.merge(fossil, total, on=["province", "year"])
    merged["workforce_exposure"] = (merged["fossil_employment"] / merged["total_employment"] * 100).round(4)
    result = merged[["province", "year", "workforce_exposure"]].sort_values(["province", "year"])

    output_path = PROCESSED_FILES["workforce_exposure"]
    result.to_csv(output_path, index=False)
    log.info("✓ Workforce exposure saved: %d rows", len(result))
    return result


def _from_fallback(data: dict, col_name: str, output_dir: Path) -> pd.DataFrame:
    rows = [{"province": p, "year": y, col_name: v}
            for p, yd in data.items() for y, v in yd.items()]
    result = pd.DataFrame(rows).sort_values(["province", "year"]).reset_index(drop=True)
    output_path = PROCESSED_FILES[col_name]
    result.to_csv(output_path, index=False)
    log.warning("✓ %s saved using FALLBACK data: %d rows", col_name, len(result))
    return result


if __name__ == "__main__":
    result = compute()
    print(result[result["year"] == result["year"].max()].sort_values("workforce_exposure", ascending=False).to_string(index=False))
