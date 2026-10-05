"""
pipeline/constants.py
======================
Shared constants used across the entire CETR Index pipeline.
Import from here — never hardcode province names, NAICS codes,
or file paths in individual scripts.

Author : Ved
Updated: 2026-05-24
"""

from pathlib import Path

# ── Project root ────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
DATA_RAW       = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
DATA_INDEX     = ROOT / "data" / "index"
DOCS           = ROOT / "docs"
METHODOLOGY    = ROOT / "methodology.json"

# ── Province mapping ─────────────────────────────────────────────────────────
# Keys: full Stats Canada names. Values: 2-letter abbreviations.
PROVINCE_MAP: dict[str, str] = {
    "Alberta":                      "AB",
    "British Columbia":             "BC",
    "Manitoba":                     "MB",
    "New Brunswick":                "NB",
    "Newfoundland and Labrador":    "NL",
    "Nova Scotia":                  "NS",
    "Ontario":                      "ON",
    "Prince Edward Island":         "PE",
    "Quebec":                       "QC",
    "Saskatchewan":                 "SK",
}
PROVINCE_ABBREVS = list(PROVINCE_MAP.values())  # ['AB', 'BC', ...]
PROVINCE_NAMES   = {v: k for k, v in PROVINCE_MAP.items()}  # reverse lookup

# Provinces excluded from index (insufficient data)
EXCLUDED_TERRITORIES = ["YT", "NT", "NU", "Yukon", "Northwest Territories", "Nunavut"]

# ── NAICS codes for fossil fuel industries ───────────────────────────────────
# Used in both stranded_asset_risk and workforce_exposure scripts.
# Source: Statistics Canada NAICS 2022 classification
FOSSIL_FUEL_NAICS = [
    "Oil and gas extraction",
    "Crude petroleum extraction",
    "Natural gas extraction",
    "Natural gas liquid extraction",
    "Bituminous coal and lignite surface mining",
    "Services to oil and gas extraction",
    "Petroleum and coal products manufacturing",
    "Support activities for mining, and oil and gas extraction",
]

# More general pattern matching (some SC tables use abbreviated names)
FOSSIL_FUEL_NAICS_PATTERNS = [
    "oil and gas",
    "coal mining",
    "petroleum",
    "bituminous",
    "crude petroleum",
    "natural gas extraction",
    "services to oil",
    "support activities for oil",
]

# ── Statistics Canada table IDs ─────────────────────────────────────────────
STATCAN_TABLES = {
    "gdp_by_industry":        "36-10-0402-01",
    "employment_by_industry": "14-10-0023-01",
    "household_spending":     "11-10-0223-01",
}

# ── CER direct CSV endpoints ────────────────────────────────────────────────
CER_ENDPOINTS = {
    "electricity_generation": "https://www.cer-rec.gc.ca/open/energy/electricity-generation-dataset.csv",
    "electricity_capacity":   "https://www.cer-rec.gc.ca/open/energy/electricity-capacity-dataset.csv",
}

# ── Processed file names ─────────────────────────────────────────────────────
PROCESSED_FILES = {
    "carbon_intensity":    DATA_PROCESSED / "carbon_intensity.csv",
    "stranded_asset_risk": DATA_PROCESSED / "stranded_asset_risk.csv",
    "grid_reliability":    DATA_PROCESSED / "grid_reliability.csv",
    "energy_poverty":      DATA_PROCESSED / "energy_poverty.csv",
    "workforce_exposure":  DATA_PROCESSED / "workforce_exposure.csv",
}

# ── Index output files ────────────────────────────────────────────────────────
INDEX_FILES = {
    "full":               DATA_INDEX / "cetr_index_full.csv",
    "latest_json":        DATA_INDEX / "cetr_index_latest.json",
    "sensitivity":        DATA_INDEX / "sensitivity_analysis.csv",
    "monetary":           DATA_INDEX / "monetary_valuation.csv",
}

# ── Scoring configuration ─────────────────────────────────────────────────────
# Loaded from methodology.json at runtime, but defined here as fallback
DEFAULT_WEIGHTS = {
    "carbon_intensity":    0.25,
    "stranded_asset_risk": 0.25,
    "grid_reliability":    0.20,
    "energy_poverty":      0.15,
    "workforce_exposure":  0.15,
}

# Years to include in the index
FIRST_YEAR = 2010
# LAST_YEAR is determined dynamically from available data

# ── Energy poverty threshold ──────────────────────────────────────────────────
ENERGY_POVERTY_THRESHOLD_PCT = 6.0  # % of household income

# ── HTTP request settings ─────────────────────────────────────────────────────
REQUEST_TIMEOUT  = 60   # seconds
REQUEST_RETRIES  = 3
REQUEST_BACKOFF  = 2.0  # seconds between retries (doubles each time)
REQUEST_DELAY    = 1.0  # polite delay between API calls

# ── Logging format ────────────────────────────────────────────────────────────
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE   = "%Y-%m-%d %H:%M:%S"
