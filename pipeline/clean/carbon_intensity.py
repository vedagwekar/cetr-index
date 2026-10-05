"""
pipeline/clean/carbon_intensity.py
====================================
Computes electricity sector carbon intensity (tCO2/MWh) by province
and year. This is the ratio of electricity-sector GHG emissions to
total electricity generation.

Inputs
------
  data/raw/eccc_ghg_annex13.xlsx      — ECCC National GHG Inventory,
                                         Annex 13, manually downloaded annually
  data/raw/cer_generation_totals.csv  — CER electricity generation,
                                         fetched by pipeline/ingest/cer_client.py

Output
------
  data/processed/carbon_intensity.csv
  Columns: province (str, 2-letter), year (int), carbon_intensity (float, tCO2/MWh)

Formula
-------
  carbon_intensity = (emissions_mt × 1e6) / (total_generation_gwh × 1e3)

  Units: Mt × 1e6 = tonnes; GWh × 1e3 = MWh → result in tCO2/MWh

Notes
-----
  ECCC data lags ~18 months. If the latest generation year has no
  matching emissions year, the prior emissions year is used with
  a warning logged. See docs/decisions.md §3.1.

Author : Ved
Updated: 2026-05-24
"""

import logging
from pathlib import Path

import pandas as pd

from pipeline.constants import (
    DATA_PROCESSED,
    DATA_RAW,
    LOG_DATE,
    LOG_FORMAT,
    PROCESSED_FILES,
    PROVINCE_MAP,
)

logging.basicConfig(format=LOG_FORMAT, datefmt=LOG_DATE, level=logging.INFO)
log = logging.getLogger("clean.carbon_intensity")

# ECCC Annex 13 sheet name and expected structure.
# These are the sheet names as of the 2024 NIR — verify annually.
ECCC_SHEET_CANDIDATES = [
    "A13-5",        # Most common
    "Table A13-5",
    "Annex 13-5",
    "A13.5",
]

# The ECCC uses these province name variants (different from Stats Canada)
ECCC_PROVINCE_MAP: dict[str, str] = {
    **PROVINCE_MAP,  # inherit all Stats Canada mappings
    "Newfoundland & Labrador": "NL",
    "Newfoundland": "NL",
    "P.E.I.": "PE",
    "Prince Edward Is.": "PE",
    "B.C.": "BC",
    "N.B.": "NB",
    "N.S.": "NS",
    "Que.": "QC",
    "Ont.": "ON",
    "Man.": "MB",
    "Sask.": "SK",
    "Alta.": "AB",
}


def _load_eccc_annex13(raw_dir: Path) -> pd.DataFrame | None:
    """
    Load ECCC GHG inventory Annex 13 (electricity sector emissions by province).

    Returns a long-format DataFrame: province | year | emissions_mt
    Returns None if the file doesn't exist (handled by caller).
    """
    xlsx_path = raw_dir / "eccc_ghg_annex13.xlsx"
    if not xlsx_path.exists():
        log.warning(
            "ECCC GHG inventory not found at %s. "
            "Carbon intensity will use FALLBACK DATA. "
            "See pipeline/ingest/cer_client.py for download instructions.",
            xlsx_path,
        )
        return None

    # Try each candidate sheet name
    xl = pd.ExcelFile(xlsx_path)
    sheet_name = None
    for candidate in ECCC_SHEET_CANDIDATES:
        if candidate in xl.sheet_names:
            sheet_name = candidate
            break

    if sheet_name is None:
        log.warning(
            "None of the expected sheet names found in %s. "
            "Available sheets: %s",
            xlsx_path.name, xl.sheet_names,
        )
        # Try the first sheet that looks like Annex 13
        for s in xl.sheet_names:
            if "13" in s or "electricity" in s.lower():
                sheet_name = s
                log.info("Using sheet: %s", sheet_name)
                break

    if sheet_name is None:
        log.error("Could not identify Annex 13 sheet. Please check the Excel file manually.")
        return None

    # ECCC Excel has a complex header structure — skip rows until we find the data
    # Pattern: province names appear in column A, years in row 1
    df_raw = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=None, engine="openpyxl")

    # Find the header row: the row containing year numbers
    header_row_idx = None
    for i, row in df_raw.iterrows():
        if pd.to_numeric(row, errors="coerce").notna().sum() >= 5:
            year_candidates = pd.to_numeric(row, errors="coerce").dropna()
            if any(1990 <= y <= 2030 for y in year_candidates):
                header_row_idx = i
                break

    if header_row_idx is None:
        log.error("Could not find year header row in ECCC Annex 13.")
        return None

    # Re-read with the correct header
    df = pd.read_excel(
        xlsx_path, sheet_name=sheet_name,
        header=header_row_idx, engine="openpyxl",
    )

    # The first column should be province names
    province_col = df.columns[0]
    df = df.rename(columns={province_col: "province_raw"})
    df["province_raw"] = df["province_raw"].astype(str).str.strip()

    # Map province names → abbreviations
    df["province"] = df["province_raw"].map(ECCC_PROVINCE_MAP)
    df = df[df["province"].notna()].copy()

    # Melt from wide (years as columns) to long format
    year_cols = [c for c in df.columns if str(c).isdigit() and 1990 <= int(str(c)) <= 2030]

    if not year_cols:
        # Columns might be formatted as floats: 2020.0
        year_cols = [c for c in df.columns
                     if pd.notna(c) and str(c).replace(".0", "").isdigit()
                     and 1990 <= int(str(c).replace(".0", "")) <= 2030]

    if not year_cols:
        log.error("No year columns found in ECCC Annex 13. Columns: %s", list(df.columns[:20]))
        return None

    df_long = df[["province"] + year_cols].melt(
        id_vars="province",
        var_name="year",
        value_name="emissions_mt",
    )
    df_long["year"] = pd.to_numeric(
        df_long["year"].astype(str).str.replace(".0", "", regex=False),
        errors="coerce"
    ).astype("Int64")
    df_long["emissions_mt"] = pd.to_numeric(df_long["emissions_mt"], errors="coerce")
    df_long = df_long.dropna(subset=["year", "emissions_mt"])

    log.info("ECCC Annex 13 loaded: %d province-years", len(df_long))
    return df_long


def _load_fallback_emissions() -> pd.DataFrame:
    """
    Hardcoded fallback emissions data for testing when ECCC file is unavailable.
    Values are approximate, based on published Canadian GHG inventory summaries.
    DO NOT USE IN PRODUCTION — replace with real ECCC data.

    Units: Mt CO2-equivalent (electricity sector only)
    """
    log.warning("Using FALLBACK emissions data — for development only!")
    data = {
        # Province, 2020, 2021 (approx Mt CO2e electricity sector)
        ("AB", 2020): 30.5, ("AB", 2021): 29.8,
        ("BC", 2020): 0.5,  ("BC", 2021): 0.5,
        ("MB", 2020): 0.3,  ("MB", 2021): 0.3,
        ("NB", 2020): 2.1,  ("NB", 2021): 1.8,
        ("NL", 2020): 0.1,  ("NL", 2021): 0.1,
        ("NS", 2020): 4.2,  ("NS", 2021): 3.9,
        ("ON", 2020): 2.1,  ("ON", 2021): 2.0,
        ("PE", 2020): 0.05, ("PE", 2021): 0.04,
        ("QC", 2020): 0.2,  ("QC", 2021): 0.2,
        ("SK", 2020): 9.8,  ("SK", 2021): 9.5,
    }
    rows = [{"province": k[0], "year": k[1], "emissions_mt": v} for k, v in data.items()]
    return pd.DataFrame(rows)


def compute(
    raw_dir: Path = DATA_RAW,
    output_dir: Path = DATA_PROCESSED,
) -> pd.DataFrame:
    """
    Compute carbon intensity (tCO2/MWh) per province per year.

    Parameters
    ----------
    raw_dir : Path
    output_dir : Path

    Returns
    -------
    pd.DataFrame
        Columns: province (str), year (int), carbon_intensity (float)
        One row per province-year with valid data.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Load emissions ────────────────────────────────────────────────────────
    emissions = _load_eccc_annex13(raw_dir)
    if emissions is None:
        emissions = _load_fallback_emissions()

    # ── Load generation ───────────────────────────────────────────────────────
    gen_path = raw_dir / "cer_generation_totals.csv"
    if not gen_path.exists():
        log.error(
            "CER generation totals not found at %s. "
            "Run: python -m pipeline.ingest.cer_client",
            gen_path,
        )
        return pd.DataFrame(columns=["province", "year", "carbon_intensity"])

    generation = pd.read_csv(gen_path)
    generation["year"] = pd.to_numeric(generation["year"], errors="coerce").astype("Int64")
    log.info("CER generation loaded: %d province-years", len(generation))

    # ── Merge on province + year ──────────────────────────────────────────────
    merged = pd.merge(
        emissions, generation,
        on=["province", "year"],
        how="inner",
    )
    log.info("After merge: %d province-years with both emissions and generation", len(merged))

    if len(merged) == 0:
        log.error("Merge produced 0 rows — check that province names and years align.")
        return pd.DataFrame(columns=["province", "year", "carbon_intensity"])

    # ── Calculate carbon intensity ────────────────────────────────────────────
    # emissions in Mt CO2e, generation in GWh
    # tCO2/MWh = (Mt × 1e6 tonnes/Mt) / (GWh × 1e3 MWh/GWh)
    merged["carbon_intensity"] = (
        merged["emissions_mt"] * 1_000_000
        / (merged["total_generation_gwh"] * 1_000)
    ).round(6)

    # Sanity checks — log warnings but don't drop data
    negative = merged["carbon_intensity"] < 0
    if negative.any():
        log.warning("Negative carbon intensity values found (impossible): %s",
                    merged[negative][["province", "year", "carbon_intensity"]])

    extreme = merged["carbon_intensity"] > 2.0
    if extreme.any():
        log.warning(
            "Carbon intensity > 2.0 tCO2/MWh (very high — check data): %s",
            merged[extreme][["province", "year", "carbon_intensity"]],
        )

    result = merged[["province", "year", "carbon_intensity"]].copy()
    result = result.sort_values(["province", "year"]).reset_index(drop=True)

    # ── Save ──────────────────────────────────────────────────────────────────
    output_path = PROCESSED_FILES["carbon_intensity"]
    result.to_csv(output_path, index=False)
    log.info("✓ Carbon intensity saved: %d rows to %s", len(result), output_path.name)

    # Log summary stats
    latest_year = result["year"].max()
    latest = result[result["year"] == latest_year].sort_values("carbon_intensity", ascending=False)
    log.info("Latest year (%d) carbon intensity (tCO2/MWh):", latest_year)
    for _, row in latest.iterrows():
        log.info("  %s: %.4f", row["province"], row["carbon_intensity"])

    return result


if __name__ == "__main__":
    result = compute()
    print(result.to_string(index=False))
