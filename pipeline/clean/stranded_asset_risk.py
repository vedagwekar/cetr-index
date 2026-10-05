"""
pipeline/clean/stranded_asset_risk.py
=======================================
Computes fossil fuel industries as a percentage of total provincial GDP.
This metric captures economic exposure to stranded assets — the risk that
oil sands, coal mines, and gas infrastructure lose value before end of
economic life due to climate policy or technology shifts.

Input
-----
  data/raw/36-10-0402-01_raw.csv  — Stats Canada GDP by industry by province
                                     (Table 36-10-0402-01, fetched by statcan_client.py)

Output
------
  data/processed/stranded_asset_risk.csv
  Columns: province (str), year (int), stranded_asset_risk (float, % of GDP)

Formula
-------
  stranded_asset_risk = sum(fossil_fuel_industry_GDP) / total_provincial_GDP × 100

Notes
-----
  - NAICS codes for fossil fuels defined in pipeline/constants.py
  - "All industries" aggregate used as denominator for total GDP
  - Some sub-industry values are suppressed (small N) in PE and NL —
    these are handled by summing only available NAICS codes
  - See docs/decisions.md §3.2 for NAICS code selection rationale

Author : Ved
Updated: 2026-05-24
"""

import logging
from pathlib import Path

import pandas as pd

from pipeline.constants import (
    DATA_PROCESSED,
    DATA_RAW,
    FOSSIL_FUEL_NAICS,
    FOSSIL_FUEL_NAICS_PATTERNS,
    LOG_DATE,
    LOG_FORMAT,
    PROCESSED_FILES,
    STATCAN_TABLES,
)

logging.basicConfig(format=LOG_FORMAT, datefmt=LOG_DATE, level=logging.INFO)
log = logging.getLogger("clean.stranded_asset_risk")

# Fallback data for development (approximate values based on published sources)
_FALLBACK_DATA = {
    # province: {year: stranded_asset_pct}
    # Sources: Statistics Canada, AER Annual Report, provincial budgets
    "AB": {2015: 22.1, 2016: 17.8, 2017: 19.3, 2018: 21.2, 2019: 22.0,
           2020: 15.6, 2021: 19.8, 2022: 24.1},
    "SK": {2015: 11.2, 2016:  8.9, 2017:  9.4, 2018: 10.8, 2019: 11.3,
           2020:  8.1, 2021:  9.9, 2022: 12.4},
    "BC": {2015:  2.1, 2016:  1.8, 2017:  2.0, 2018:  2.3, 2019:  2.4,
           2020:  1.7, 2021:  2.0, 2022:  2.8},
    "NL": {2015: 15.3, 2016: 12.1, 2017: 12.8, 2018: 14.2, 2019: 13.9,
           2020:  9.8, 2021: 11.4, 2022: 14.1},
    "NS": {2015:  0.8, 2016:  0.6, 2017:  0.7, 2018:  0.8, 2019:  0.7,
           2020:  0.5, 2021:  0.6, 2022:  0.8},
    "NB": {2015:  1.2, 2016:  1.0, 2017:  1.1, 2018:  1.3, 2019:  1.2,
           2020:  0.9, 2021:  1.1, 2022:  1.4},
    "ON": {2015:  0.5, 2016:  0.4, 2017:  0.5, 2018:  0.5, 2019:  0.5,
           2020:  0.3, 2021:  0.4, 2022:  0.5},
    "QC": {2015:  0.3, 2016:  0.2, 2017:  0.3, 2018:  0.3, 2019:  0.3,
           2020:  0.2, 2021:  0.2, 2022:  0.3},
    "MB": {2015:  1.1, 2016:  0.9, 2017:  1.0, 2018:  1.1, 2019:  1.0,
           2020:  0.7, 2021:  0.9, 2022:  1.1},
    "PE": {2015:  0.1, 2016:  0.1, 2017:  0.1, 2018:  0.1, 2019:  0.1,
           2020:  0.1, 2021:  0.1, 2022:  0.1},
}


def _is_fossil_fuel_industry(industry_name: str) -> bool:
    """Return True if the industry name matches fossil fuel NAICS patterns."""
    lower = industry_name.lower()
    return any(pattern.lower() in lower for pattern in FOSSIL_FUEL_NAICS_PATTERNS)


def compute(
    raw_dir: Path = DATA_RAW,
    output_dir: Path = DATA_PROCESSED,
) -> pd.DataFrame:
    """
    Compute stranded asset risk (fossil GDP as % of total GDP) per province per year.

    Parameters
    ----------
    raw_dir : Path
    output_dir : Path

    Returns
    -------
    pd.DataFrame
        Columns: province (str), year (int), stranded_asset_risk (float, %)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Load Stats Canada GDP data ────────────────────────────────────────────
    table_id = STATCAN_TABLES["gdp_by_industry"]
    csv_path = raw_dir / f"{table_id}_raw.csv"

    if not csv_path.exists():
        log.warning(
            "GDP data not found at %s — using fallback data. "
            "Run: python -m pipeline.ingest.statcan_client",
            csv_path,
        )
        return _compute_from_fallback(output_dir)

    df = pd.read_csv(csv_path, encoding="latin-1", low_memory=False)
    log.info("Loaded GDP data: %d rows, %d columns", len(df), len(df.columns))

    # ── Normalize column names ─────────────────────────────────────────────────
    # Stats Canada uses verbose column names — standardize them
    col_lower = {c: c.lower() for c in df.columns}
    rename = {}
    for orig, low in col_lower.items():
        if "ref_date" in low or low == "refdate":
            rename[orig] = "year_raw"
        elif "naics" in low or "industry" in low or "classification" in low:
            rename[orig] = "industry"
        elif low == "value":
            rename[orig] = "gdp_millions"
        elif "province" in low and "geo" not in low:
            pass  # province column added by statcan_client already
    df = df.rename(columns=rename)

    # Parse year
    if "year_raw" in df.columns:
        df["year"] = pd.to_numeric(
            df["year_raw"].astype(str).str[:4], errors="coerce"
        ).astype("Int64")
    elif "REF_DATE" in df.columns:
        df["year"] = pd.to_numeric(
            df["REF_DATE"].astype(str).str[:4], errors="coerce"
        ).astype("Int64")

    # Parse GDP value
    if "gdp_millions" not in df.columns and "VALUE" in df.columns:
        df["gdp_millions"] = pd.to_numeric(df["VALUE"], errors="coerce")
    else:
        df["gdp_millions"] = pd.to_numeric(df.get("gdp_millions", pd.Series()), errors="coerce")

    # Ensure province column exists
    if "province" not in df.columns and "GEO" in df.columns:
        from pipeline.constants import PROVINCE_MAP
        df["province"] = df["GEO"].map(PROVINCE_MAP)

    # Drop rows without province (territories, national totals)
    df = df[df["province"].notna()].copy()

    # ── Compute total GDP per province per year ───────────────────────────────
    if "industry" not in df.columns:
        industry_cols = [c for c in df.columns if "naics" in c.lower() or "industry" in c.lower()]
        if industry_cols:
            df["industry"] = df[industry_cols[0]]

    # "All industries" = total GDP denominator
    total_mask = df["industry"].str.lower().str.contains("all industries", na=False)
    total_gdp = (
        df[total_mask]
        .groupby(["province", "year"])["gdp_millions"]
        .sum()
        .reset_index()
        .rename(columns={"gdp_millions": "total_gdp"})
    )
    log.info("Total GDP rows: %d", len(total_gdp))

    # ── Compute fossil fuel GDP per province per year ─────────────────────────
    fossil_mask = df["industry"].apply(_is_fossil_fuel_industry)
    fossil_gdp = (
        df[fossil_mask]
        .groupby(["province", "year"])["gdp_millions"]
        .sum()
        .reset_index()
        .rename(columns={"gdp_millions": "fossil_gdp"})
    )
    log.info("Fossil fuel GDP rows: %d (across %d matched industries)",
             len(fossil_gdp), fossil_mask.sum())

    # ── Merge and compute ratio ───────────────────────────────────────────────
    merged = pd.merge(fossil_gdp, total_gdp, on=["province", "year"], how="inner")
    merged["stranded_asset_risk"] = (
        merged["fossil_gdp"] / merged["total_gdp"] * 100
    ).round(4)

    # Validation: Alberta should always be highest
    latest = merged[merged["year"] == merged["year"].max()]
    ab_score = latest[latest["province"] == "AB"]["stranded_asset_risk"].values
    if len(ab_score) > 0:
        log.info("Alberta stranded asset risk (latest year): %.2f%%", ab_score[0])
        if ab_score[0] < 5:
            log.warning("Alberta stranded asset risk is < 5%% — check NAICS code matching")

    result = merged[["province", "year", "stranded_asset_risk"]].copy()
    result = result.sort_values(["province", "year"]).reset_index(drop=True)

    output_path = PROCESSED_FILES["stranded_asset_risk"]
    result.to_csv(output_path, index=False)
    log.info("✓ Stranded asset risk saved: %d rows to %s", len(result), output_path.name)

    return result


def _compute_from_fallback(output_dir: Path) -> pd.DataFrame:
    """Build DataFrame from hardcoded fallback values."""
    rows = []
    for province, year_data in _FALLBACK_DATA.items():
        for year, value in year_data.items():
            rows.append({"province": province, "year": year, "stranded_asset_risk": value})
    result = pd.DataFrame(rows).sort_values(["province", "year"]).reset_index(drop=True)

    output_path = PROCESSED_FILES["stranded_asset_risk"]
    result.to_csv(output_path, index=False)
    log.warning("✓ Stranded asset risk saved using FALLBACK data: %d rows", len(result))
    return result


if __name__ == "__main__":
    result = compute()
    latest = result[result["year"] == result["year"].max()].sort_values(
        "stranded_asset_risk", ascending=False
    )
    print("\nStranded asset risk, latest year:")
    print(latest.to_string(index=False))
