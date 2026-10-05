"""
tests/test_normalization.py
=============================
Unit tests for all normalization methods in pipeline/score/normalize.py.

Tests cover:
  - Correct output range [0, 100]
  - Monotonicity (higher input → higher score for risk metrics)
  - Edge cases: ties, single value, all-identical, NaN handling
  - Entropy weights: sum to 1.0, correct direction

Author : Ved
Updated: 2026-05-24
"""

import numpy as np
import pandas as pd
import pytest

from pipeline.score.normalize import (
    entropy_weights,
    min_max,
    normalize_all_methods,
    percentile_rank,
    z_score,
)


class TestPercentileRank:
    """Tests for the primary normalization method."""

    def test_output_range_0_to_100(self):
        s = pd.Series([10, 20, 30, 40, 50])
        result = percentile_rank(s)
        assert result.min() >= 0
        assert result.max() <= 100

    def test_monotonically_increasing(self):
        """Higher raw value must → higher score (higher risk)."""
        s = pd.Series([1.0, 5.0, 10.0, 50.0, 100.0])
        result = percentile_rank(s)
        for i in range(len(result) - 1):
            assert result.iloc[i] < result.iloc[i + 1], \
                f"Not monotonic at index {i}: {result.iloc[i]:.2f} >= {result.iloc[i+1]:.2f}"

    def test_handles_ties_equally(self):
        """Tied values must receive equal scores."""
        s = pd.Series([1.0, 1.0, 5.0])
        result = percentile_rank(s)
        assert result.iloc[0] == result.iloc[1], "Tied values should have equal scores"

    def test_all_identical_values(self):
        """All identical → all get same score."""
        s = pd.Series([42.0, 42.0, 42.0, 42.0])
        result = percentile_rank(s)
        assert result.nunique() == 1

    def test_single_value(self):
        """Single value should not raise."""
        s = pd.Series([99.0])
        result = percentile_rank(s)
        assert len(result) == 1
        assert 0 <= result.iloc[0] <= 100

    def test_nan_handling(self):
        """NaN inputs produce NaN outputs, non-NaN values still ranked."""
        s = pd.Series([1.0, np.nan, 3.0])
        result = percentile_rank(s)
        assert pd.isna(result.iloc[1])
        assert pd.notna(result.iloc[0])
        assert pd.notna(result.iloc[2])

    def test_preserves_index(self):
        """Output index must match input index."""
        s = pd.Series([3, 1, 2], index=["AB", "QC", "ON"])
        result = percentile_rank(s)
        assert list(result.index) == ["AB", "QC", "ON"]

    def test_n_10_provinces(self):
        """Realistic scenario: 10 provinces with actual-range values."""
        carbon_intensity = pd.Series({
            "AB": 0.72, "SK": 0.68, "NS": 0.58, "NB": 0.35, "MB": 0.018,
            "ON": 0.030, "QC": 0.003, "BC": 0.014, "NL": 0.012, "PE": 0.041,
        })
        result = percentile_rank(carbon_intensity)
        # Alberta has highest carbon intensity → must have highest score
        assert result["AB"] == result.max(), "Alberta should have highest carbon intensity score"
        # Quebec has lowest → must have lowest score
        assert result["QC"] == result.min(), "Quebec should have lowest carbon intensity score"


class TestZScore:

    def test_output_range(self):
        s = pd.Series([10, 20, 30, 40, 50])
        result = z_score(s)
        assert result.min() >= 0
        assert result.max() <= 100

    def test_monotonically_increasing(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        result = z_score(s)
        for i in range(len(result) - 1):
            assert result.iloc[i] < result.iloc[i + 1]

    def test_constant_series_returns_50(self):
        """All-same values → z=0 → score=50."""
        s = pd.Series([7.0, 7.0, 7.0])
        result = z_score(s)
        assert (result == 50.0).all()

    def test_outlier_clipping(self):
        """Values beyond 3σ should be clipped, not cause out-of-range scores."""
        s = pd.Series([1, 1, 1, 1, 1, 1, 1, 1, 1, 1000])  # extreme outlier
        result = z_score(s, clip_sigma=3.0)
        assert result.max() <= 100
        assert result.min() >= 0


class TestMinMax:

    def test_output_range(self):
        s = pd.Series([0, 25, 50, 75, 100])
        result = min_max(s)
        assert abs(result.min() - 0) < 1e-9
        assert abs(result.max() - 100) < 1e-9

    def test_monotonically_increasing(self):
        s = pd.Series([1.0, 2.0, 3.0])
        result = min_max(s)
        assert result.iloc[0] < result.iloc[1] < result.iloc[2]

    def test_constant_series_returns_50(self):
        s = pd.Series([5.0, 5.0, 5.0])
        result = min_max(s)
        assert (result == 50.0).all()


class TestEntropyWeights:

    def test_weights_sum_to_one(self):
        df = pd.DataFrame({
            "carbon_intensity":    [0.72, 0.014, 0.030, 0.003, 0.68],
            "stranded_asset_risk": [22.1, 1.2,   0.5,   0.3,  11.2],
            "workforce_exposure":  [10.8, 1.2,   0.3,   0.2,   5.2],
        }, index=["AB", "BC", "ON", "QC", "SK"])
        weights = entropy_weights(df)
        total = sum(weights.values())
        assert abs(total - 1.0) < 1e-9, f"Weights sum to {total:.6f}"

    def test_high_variance_gets_higher_weight(self):
        """The metric with more variance across provinces should get higher weight."""
        df = pd.DataFrame({
            "high_variance": [1, 10, 50, 100, 200],  # very spread
            "low_variance":  [5,  5,  6,   5,   5],  # nearly constant
        })
        weights = entropy_weights(df)
        assert weights["high_variance"] > weights["low_variance"], \
            "High-variance metric should get more weight"

    def test_all_positive_output(self):
        df = pd.DataFrame({
            "a": [1, 2, 3, 4, 5],
            "b": [5, 4, 3, 2, 1],
        })
        weights = entropy_weights(df)
        for k, v in weights.items():
            assert v >= 0, f"Weight for {k} is negative: {v}"

    def test_single_column_gets_weight_one(self):
        df = pd.DataFrame({"only": [1, 2, 3, 4, 5]})
        weights = entropy_weights(df)
        assert abs(weights["only"] - 1.0) < 1e-9

    def test_requires_at_least_two_rows(self):
        df = pd.DataFrame({"a": [1]})
        with pytest.raises(ValueError, match="at least 2"):
            entropy_weights(df)


class TestNormalizeAllMethods:

    def test_returns_three_columns(self):
        s = pd.Series([1, 2, 3, 4, 5])
        result = normalize_all_methods(s)
        assert "percentile_rank" in result.columns
        assert "z_score" in result.columns
        assert "min_max" in result.columns

    def test_all_values_in_range(self):
        s = pd.Series([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
        result = normalize_all_methods(s)
        for col in result.columns:
            assert result[col].min() >= 0, f"{col} has values < 0"
            assert result[col].max() <= 100, f"{col} has values > 100"
