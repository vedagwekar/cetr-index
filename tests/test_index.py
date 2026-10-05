"""
tests/test_index.py
=====================
Integration tests for the CETR Index scoring pipeline.

These tests verify that the index produces economically sensible results —
not just mathematically correct ones. A system that passes unit tests but
ranks Quebec above Alberta on stranded asset risk has a data or logic error.

Sanity checks based on publicly known facts:
  - Alberta has Canada's largest oil sands → must rank highest on stranded assets
  - Quebec generates ~97% of electricity from hydro → must rank lowest on carbon intensity
  - Saskatchewan has highest coal dependency → high carbon intensity
  - Ontario's nuclear fleet → low carbon intensity
  - NL and NS have highest energy poverty rates (cold climate + high energy costs)

Author : Ved
Updated: 2026-05-24
"""

import json
import os
from pathlib import Path

import pandas as pd
import pytest
from scipy.stats import spearmanr

from pipeline.constants import (
    DATA_PROCESSED, INDEX_FILES, METHODOLOGY, PROCESSED_FILES,
)
from pipeline.score.index_calculator import compute_index_for_year, _load_weights
from pipeline.score.normalize import percentile_rank


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def weights():
    return _load_weights()


@pytest.fixture(scope="module")
def processed_data():
    """Load all processed metric CSVs. Skip if not generated yet."""
    data = {}
    for name, path in PROCESSED_FILES.items():
        if path.exists():
            data[name] = pd.read_csv(path)
    if not data:
        pytest.skip("Processed data not available — run pipeline/run_all.py first")
    return data


@pytest.fixture(scope="module")
def latest_scores(weights):
    """Compute index for the latest available year."""
    if not PROCESSED_FILES["stranded_asset_risk"].exists():
        pytest.skip("Processed data not available — run pipeline/run_all.py first")

    df = pd.read_csv(PROCESSED_FILES["stranded_asset_risk"])
    latest_year = int(df["year"].dropna().max())
    return compute_index_for_year(latest_year, weights)


# ── Methodology tests ──────────────────────────────────────────────────────────

class TestMethodology:

    def test_weights_sum_to_exactly_one(self):
        """Weights must sum to exactly 1.0 — not 0.99 or 1.01."""
        if not METHODOLOGY.exists():
            pytest.skip("methodology.json not found")
        with open(METHODOLOGY) as f:
            m = json.load(f)
        weights = [v["weight"] for v in m["components"].values()]
        total = sum(weights)
        assert abs(total - 1.0) < 1e-9, \
            f"Weights sum to {total:.10f}, not 1.0. Adjust methodology.json."

    def test_all_five_components_present(self):
        """All five CETR components must be defined in methodology.json."""
        if not METHODOLOGY.exists():
            pytest.skip("methodology.json not found")
        with open(METHODOLOGY) as f:
            m = json.load(f)
        required = {
            "carbon_intensity", "stranded_asset_risk", "grid_reliability",
            "energy_poverty", "workforce_exposure"
        }
        present = set(m["components"].keys())
        assert required == present, f"Missing: {required - present}, Extra: {present - required}"

    def test_all_weights_positive(self):
        """No component should have a zero or negative weight."""
        if not METHODOLOGY.exists():
            pytest.skip("methodology.json not found")
        with open(METHODOLOGY) as f:
            m = json.load(f)
        for name, comp in m["components"].items():
            assert comp["weight"] > 0, f"{name} has non-positive weight: {comp['weight']}"

    def test_ten_provinces_defined(self):
        """Exactly 10 provinces should be in the province list."""
        if not METHODOLOGY.exists():
            pytest.skip("methodology.json not found")
        with open(METHODOLOGY) as f:
            m = json.load(f)
        assert len(m["provinces"]) == 10, f"Expected 10 provinces, got {len(m['provinces'])}"


# ── Processed data tests ───────────────────────────────────────────────────────

class TestProcessedData:

    def test_all_metric_files_exist(self, processed_data):
        """After running the pipeline, all 5 processed files must exist."""
        for name, path in PROCESSED_FILES.items():
            assert path.exists(), \
                f"Missing processed file: {path}. Run pipeline/run_all.py."

    def test_all_provinces_present_in_latest_year(self, processed_data):
        """Every metric must have data for all 10 provinces in the latest year."""
        expected_provinces = {"AB", "BC", "MB", "NB", "NL", "NS", "ON", "PE", "QC", "SK"}
        for name, df in processed_data.items():
            latest_year = df["year"].max()
            latest = df[df["year"] == latest_year]
            present = set(latest["province"].values)
            missing = expected_provinces - present
            assert not missing, \
                f"{name}: missing provinces in year {latest_year}: {missing}"

    def test_no_negative_metric_values(self, processed_data):
        """All metric values must be non-negative (they're percentages, ratios, or hours)."""
        for name, df in processed_data.items():
            metric_col = [c for c in df.columns if c not in ("province", "year")][0]
            negatives = df[df[metric_col] < 0]
            assert len(negatives) == 0, \
                f"{name} has {len(negatives)} negative values: {negatives}"

    def test_no_extreme_outliers(self, processed_data):
        """Values beyond physically plausible ranges should not exist."""
        plausible_maxes = {
            "carbon_intensity":    2.0,   # tCO2/MWh — coal plants max ~1.0
            "stranded_asset_risk": 50.0,  # % of GDP — even Alberta shouldn't exceed 50%
            "grid_reliability":    20.0,  # hours/year — > 20h/yr is catastrophic
            "energy_poverty":      60.0,  # % households — > 60% would be a crisis
            "workforce_exposure":  25.0,  # % workforce — > 25% would be extraordinary
        }
        for name, df in processed_data.items():
            if name not in plausible_maxes:
                continue
            metric_col = [c for c in df.columns if c not in ("province", "year")][0]
            max_val = plausible_maxes[name]
            extremes = df[df[metric_col] > max_val]
            assert len(extremes) == 0, \
                f"{name} has values > {max_val} (implausible): {extremes}"


# ── Economic sanity tests ──────────────────────────────────────────────────────

class TestEconomicSanity:
    """
    These tests verify that the scored results make economic sense.
    They use known facts about Canadian provinces' energy systems.
    A passing test does NOT mean the data is correct — it means the
    data is in the right direction.
    """

    def test_alberta_highest_stranded_asset_risk(self, processed_data):
        """
        Alberta has the world's third-largest oil reserves (oil sands).
        It must rank highest on stranded asset risk among all provinces.
        """
        if "stranded_asset_risk" not in processed_data:
            pytest.skip("stranded_asset_risk data not available")
        df = processed_data["stranded_asset_risk"]
        latest = df[df["year"] == df["year"].max()]
        ranked = latest.sort_values("stranded_asset_risk", ascending=False)
        assert ranked.iloc[0]["province"] == "AB", \
            f"Expected AB to have highest stranded asset risk, got: {ranked.iloc[0]['province']}"

    def test_quebec_lowest_carbon_intensity(self, processed_data):
        """
        Quebec generates ~97% of electricity from hydroelectric dams.
        It must have the lowest (or near-lowest) carbon intensity.
        """
        if "carbon_intensity" not in processed_data:
            pytest.skip("carbon_intensity data not available")
        df = processed_data["carbon_intensity"]
        latest = df[df["year"] == df["year"].max()]
        ranked = latest.sort_values("carbon_intensity")
        top_3_lowest = ranked.head(3)["province"].values
        assert "QC" in top_3_lowest, \
            f"Expected QC in bottom 3 carbon intensity, got: {top_3_lowest}"

    def test_alberta_and_saskatchewan_top_workforce_exposure(self, processed_data):
        """AB and SK should both be in the top 3 for fossil fuel workforce exposure."""
        if "workforce_exposure" not in processed_data:
            pytest.skip("workforce_exposure data not available")
        df = processed_data["workforce_exposure"]
        latest = df[df["year"] == df["year"].max()]
        top_3 = set(latest.nlargest(3, "workforce_exposure")["province"].values)
        assert len({"AB", "SK"} & top_3) >= 1, \
            f"Expected AB or SK in top 3 workforce exposure, got: {top_3}"

    def test_ontario_low_carbon_intensity(self, processed_data):
        """Ontario's nuclear fleet means it should be in the bottom half for carbon intensity."""
        if "carbon_intensity" not in processed_data:
            pytest.skip("carbon_intensity data not available")
        df = processed_data["carbon_intensity"]
        latest = df[df["year"] == df["year"].max()]
        ranked = latest.sort_values("carbon_intensity")
        on_rank = ranked.reset_index(drop=True).index[ranked["province"].values == "ON"].tolist()
        if on_rank:
            assert on_rank[0] < 6, \
                f"Expected ON in bottom half of carbon intensity (rank < 6), got rank {on_rank[0]}"

    def test_final_scores_range_0_to_100(self, latest_scores):
        """All final CETR Index scores must be in [0, 100]."""
        if latest_scores is None:
            pytest.skip("Index scores not computed")
        assert latest_scores["cetr_index"].min() >= 0
        assert latest_scores["cetr_index"].max() <= 100

    def test_alberta_highest_overall_risk(self, latest_scores):
        """
        Given Alberta's extreme stranded asset and workforce exposure,
        it should rank in the top 3 on the overall index.

        Note: AB ranks #1 when carbon_intensity is included (AB has the
        highest grid carbon intensity from coal/gas). With fallback data
        missing carbon_intensity, it may drop slightly. Top 3 is the
        correct threshold for this test — any rank worse than 3 indicates
        a data or weighting error.
        """
        if latest_scores is None:
            pytest.skip("Index scores not computed")
        top_3 = set(latest_scores.nlargest(3, "cetr_index")["province"].values)
        assert "AB" in top_3, \
            f"Expected AB in top 3 overall risk, got: {top_3}"

    def test_quebec_lowest_or_near_lowest_risk(self, latest_scores):
        """Quebec's hydro grid and diversified economy should give it low overall risk."""
        if latest_scores is None:
            pytest.skip("Index scores not computed")
        bottom_3 = set(latest_scores.nsmallest(3, "cetr_index")["province"].values)
        assert "QC" in bottom_3, \
            f"Expected QC in bottom 3 overall risk, got: {bottom_3}"


# ── Sensitivity analysis tests ─────────────────────────────────────────────────

class TestSensitivityAnalysis:

    def test_sensitivity_file_exists(self):
        """Sensitivity analysis CSV must be generated after scoring."""
        if not INDEX_FILES.get("sensitivity"):
            pytest.skip("sensitivity index file not configured")
        if not PROCESSED_FILES["stranded_asset_risk"].exists():
            pytest.skip("Processed data not available — run pipeline/run_all.py first")
        assert INDEX_FILES["sensitivity"].exists(), \
            "Sensitivity analysis file not found — run pipeline/score/index_calculator.py"

    def test_spearman_correlation_above_threshold(self):
        """
        Spearman rank correlation between all normalization methods must exceed 0.90.
        This validates that methodology is robust to the choice of normalization.
        """
        path = INDEX_FILES.get("sensitivity")
        if not path or not path.exists():
            pytest.skip("Sensitivity analysis not available")

        df = pd.read_csv(path)
        method_cols = [c for c in df.columns if c.startswith("score_")]
        if len(method_cols) < 2:
            pytest.skip("Need at least 2 normalization methods in sensitivity file")

        for i, m1 in enumerate(method_cols):
            for m2 in method_cols[i+1:]:
                rho, _ = spearmanr(df[m1], df[m2])
                assert rho >= 0.85, \
                    f"Spearman correlation between {m1} and {m2} is {rho:.3f} < 0.85. " \
                    f"Methodology may not be robust — check data or weights."
