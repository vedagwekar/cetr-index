"""
pipeline/score/index_calculator.py
=====================================
Combines all five cleaned metric CSVs into the CETR Index.

For each year:
  1. Load all five processed metric CSVs
  2. Join on province
  3. Normalize each metric using percentile rank (primary method)
  4. Apply weighted average using weights from methodology.json
  5. Output scored DataFrame

Additionally computes:
  - Sensitivity analysis (all 4 normalization methods, compare rankings)
  - Spearman rank correlation between methods
  - Monetary valuation of stranded asset risk

Usage
-----
  python -m pipeline.score.index_calculator
  # → writes to data/index/

  from pipeline.score.index_calculator import run_all_years
  df = run_all_years()

Author : Ved
Updated: 2026-05-24
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from pipeline.constants import (
    DATA_INDEX, DATA_PROCESSED, DEFAULT_WEIGHTS,
    INDEX_FILES, LOG_DATE, LOG_FORMAT,
    METHODOLOGY, PROCESSED_FILES, PROVINCE_ABBREVS, PROVINCE_NAMES,
)
from pipeline.score.normalize import (
    entropy_weights, min_max, normalize_all_methods, percentile_rank, z_score,
)

logging.basicConfig(format=LOG_FORMAT, datefmt=LOG_DATE, level=logging.INFO)
log = logging.getLogger("score.index_calculator")

RISK_BANDS = [
    (0,  33,  "Low"),
    (33, 66,  "Medium"),
    (66, 100, "High"),
]


def _load_weights() -> dict[str, float]:
    """
    Load component weights from methodology.json.
    Falls back to DEFAULT_WEIGHTS if file not found.
    """
    try:
        with open(METHODOLOGY) as f:
            m = json.load(f)
        weights = {k: v["weight"] for k, v in m["components"].items()}
        total = sum(weights.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"Weights sum to {total:.6f}, not 1.0")
        log.info("Loaded weights from methodology.json: %s", weights)
        return weights
    except (FileNotFoundError, KeyError, ValueError) as e:
        log.warning("Could not load weights from methodology.json (%s) — using defaults", e)
        return DEFAULT_WEIGHTS


def _get_risk_level(score: float) -> str:
    for lo, hi, label in RISK_BANDS:
        if lo <= score <= hi:
            return label
    return "High"


def _load_all_metrics(year: int | None = None) -> pd.DataFrame | None:
    """
    Load all five processed metric CSVs and join on province (and year).

    Parameters
    ----------
    year : int | None
        If provided, filter to this year only.
        If None, return all years (used for time series).

    Returns
    -------
    pd.DataFrame | None
        Columns: province, year, carbon_intensity, stranded_asset_risk,
                 grid_reliability, energy_poverty, workforce_exposure
        Returns None if no data found.
    """
    dfs = []
    missing_metrics = []

    for metric_name, file_path in PROCESSED_FILES.items():
        if not file_path.exists():
            log.warning("Missing processed file: %s — run pipeline/run_all.py", file_path.name)
            missing_metrics.append(metric_name)
            continue

        df = pd.read_csv(file_path)
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")

        if year is not None:
            df = df[df["year"] == year]

        if len(df) == 0:
            log.warning("No data for year %s in %s", year, file_path.name)
            continue

        dfs.append(df.rename(columns={df.columns[-1]: metric_name}))

    if not dfs:
        log.error("No metric data loaded.")
        return None

    # Join all metrics on province + year
    base = dfs[0]
    for df in dfs[1:]:
        base = pd.merge(base, df, on=["province", "year"], how="outer")

    if missing_metrics:
        log.warning("Missing metrics (will be NaN in output): %s", missing_metrics)

    return base


def compute_index_for_year(year: int, weights: dict[str, float]) -> pd.DataFrame | None:
    """
    Compute CETR Index scores for all provinces for a single year.

    Parameters
    ----------
    year : int
    weights : dict[str, float]

    Returns
    -------
    pd.DataFrame | None
        Full scored DataFrame with normalized component scores and final index.
    """
    base = _load_all_metrics(year=year)
    if base is None or len(base) == 0:
        return None

    metric_cols = [c for c in PROCESSED_FILES.keys() if c in base.columns]

    if not metric_cols:
        log.error("No metric columns found for year %d", year)
        return None

    # Normalize each metric using percentile rank (primary method)
    for col in metric_cols:
        score_col = f"{col}_score"
        base[score_col] = percentile_rank(base[col])

    # Weighted average of normalized scores
    score_cols = [f"{col}_score" for col in metric_cols]
    available_weights = {col: weights.get(col, 0) for col in metric_cols}

    # Renormalize weights if some metrics are missing
    total_available_weight = sum(available_weights.values())
    if total_available_weight == 0:
        log.error("No valid weights for available metrics")
        return None

    base["cetr_index"] = sum(
        base[f"{col}_score"] * (w / total_available_weight)
        for col, w in available_weights.items()
        if f"{col}_score" in base.columns
    )
    base["cetr_index"] = base["cetr_index"].round(2)
    base["year"] = year
    base["risk_level"] = base["cetr_index"].apply(_get_risk_level)
    base["province_name"] = base["province"].map(PROVINCE_NAMES)

    return base.sort_values("cetr_index", ascending=False).reset_index(drop=True)


def run_all_years() -> pd.DataFrame:
    """
    Compute CETR Index for all available years.

    Returns
    -------
    pd.DataFrame
        All provinces × all years, sorted by year desc, score desc.
    """
    DATA_INDEX.mkdir(parents=True, exist_ok=True)
    weights = _load_weights()

    # Determine available years from the most-populated metric
    sample_df = pd.read_csv(PROCESSED_FILES["stranded_asset_risk"]) \
        if PROCESSED_FILES["stranded_asset_risk"].exists() else pd.DataFrame()
    if sample_df.empty:
        log.error("No data available. Run pipeline/run_all.py first.")
        return pd.DataFrame()

    available_years = sorted(sample_df["year"].dropna().unique().astype(int))
    log.info("Computing index for years: %s", available_years)

    all_results = []
    for year in available_years:
        result = compute_index_for_year(year, weights)
        if result is not None and len(result) > 0:
            all_results.append(result)
            log.info("Year %d: %d provinces scored (top: %s %.1f)",
                     year, len(result),
                     result.iloc[0]["province"], result.iloc[0]["cetr_index"])
        else:
            log.warning("Year %d: no scores computed", year)

    if not all_results:
        log.error("No results computed for any year")
        return pd.DataFrame()

    combined = pd.concat(all_results, ignore_index=True)

    # ── Save full dataset ─────────────────────────────────────────────────────
    combined.to_csv(INDEX_FILES["full"], index=False)
    log.info("✓ Full index saved: %s (%d rows)", INDEX_FILES["full"].name, len(combined))

    # ── Save latest year as JSON (for frontend) ───────────────────────────────
    latest_year = int(combined["year"].max())
    latest = combined[combined["year"] == latest_year].copy()
    latest_records = latest.to_dict(orient="records")

    with open(INDEX_FILES["latest_json"], "w") as f:
        json.dump({
            "meta": {
                "version": "1.0.0",
                "last_updated": datetime.utcnow().isoformat(),
                "latest_year": latest_year,
                "methodology_url": "https://github.com/vedagwekar/cetr-index/blob/main/docs/decisions.md",
                "repository": "https://github.com/vedagwekar/cetr-index",
            },
            "data": latest_records,
        }, f, indent=2, default=str)
    log.info("✓ Latest JSON saved: %s", INDEX_FILES["latest_json"].name)

    # ── Sensitivity analysis ──────────────────────────────────────────────────
    _run_sensitivity_analysis(latest_year, weights)

    # ── Print summary ─────────────────────────────────────────────────────────
    log.info("\n" + "=" * 50)
    log.info("CETR INDEX — %d RESULTS", latest_year)
    log.info("=" * 50)
    for _, row in latest.iterrows():
        bar = "█" * int(row["cetr_index"] / 5)
        log.info("  %s  %s  %5.1f  %s",
                 row["province"], bar.ljust(20), row["cetr_index"], row["risk_level"])

    return combined


def _run_sensitivity_analysis(year: int, weights: dict[str, float]) -> None:
    """
    Compare all normalization methods for the given year.
    Computes Spearman rank correlations and logs warnings if < 0.90.
    Saves to data/index/sensitivity_analysis.csv.
    """
    log.info("\nRunning sensitivity analysis (year %d)...", year)

    base = _load_all_metrics(year=year)
    if base is None:
        return

    metric_cols = [c for c in PROCESSED_FILES.keys() if c in base.columns]
    province_col = base["province"]

    results = {"province": province_col.values}

    # Method 1: Percentile rank (primary)
    scores_pct = sum(
        percentile_rank(base[col]) * weights.get(col, 0)
        for col in metric_cols
    )
    results["score_percentile_rank"] = scores_pct.round(2).values

    # Method 2: Z-score
    scores_z = sum(
        z_score(base[col]) * weights.get(col, 0)
        for col in metric_cols
    )
    results["score_z_score"] = scores_z.round(2).values

    # Method 3: Min-max
    scores_mm = sum(
        min_max(base[col]) * weights.get(col, 0)
        for col in metric_cols
    )
    results["score_min_max"] = scores_mm.round(2).values

    # Method 4: Entropy weights
    metric_matrix = base[metric_cols].fillna(base[metric_cols].median())
    try:
        ew = entropy_weights(metric_matrix.set_index(base["province"]))
        scores_ew = sum(
            percentile_rank(base[col]) * ew.get(col, 1/len(metric_cols))
            for col in metric_cols
        )
        results["score_entropy_weighted"] = scores_ew.round(2).values
    except Exception as e:
        log.warning("Entropy weighting failed: %s", e)
        results["score_entropy_weighted"] = results["score_percentile_rank"]

    sensitivity_df = pd.DataFrame(results)

    # Spearman correlations between all method pairs
    method_cols = [c for c in sensitivity_df.columns if c.startswith("score_")]
    log.info("\nSpearman rank correlations between normalization methods:")
    log.info("  (Values > 0.90 indicate robust methodology)")
    min_corr = 1.0
    for i, m1 in enumerate(method_cols):
        for m2 in method_cols[i+1:]:
            rho, pval = spearmanr(sensitivity_df[m1], sensitivity_df[m2])
            flag = "✓" if rho >= 0.90 else "⚠ BELOW TARGET"
            log.info("  %s vs %s: ρ = %.3f %s", m1, m2, rho, flag)
            min_corr = min(min_corr, rho)

    if min_corr < 0.90:
        log.warning(
            "Minimum Spearman correlation (%.3f) is below 0.90 target. "
            "Consider reviewing methodology weights or checking for data errors.",
            min_corr
        )

    sensitivity_df.to_csv(INDEX_FILES["sensitivity"], index=False)
    log.info("✓ Sensitivity analysis saved: %s", INDEX_FILES["sensitivity"].name)


if __name__ == "__main__":
    combined = run_all_years()
    if not combined.empty:
        print(f"\nIndex computed: {len(combined)} rows across {combined['year'].nunique()} years")
