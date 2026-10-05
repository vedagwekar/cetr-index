"""
pipeline/score/normalize.py
=============================
All four normalization methods used by the CETR Index.

Methods
-------
percentile_rank  — primary method (recommended for N=10)
z_score          — sensitivity analysis comparison
min_max          — sensitivity analysis comparison
entropy_weights  — data-driven weighting (used in sensitivity analysis)

All methods produce scores in [0, 100] where higher = more risk.
Each function takes a pd.Series and returns a pd.Series of the same length.

Reference: OECD Handbook on Constructing Composite Indicators (2008), Ch. 3
Author   : Ved
Updated  : 2026-05-24
"""

import logging

import numpy as np
import pandas as pd

log = logging.getLogger("score.normalize")


def percentile_rank(series: pd.Series) -> pd.Series:
    """
    Convert raw values to percentile ranks (0–100, higher = more risk).

    Each value is ranked within the series, then expressed as a percentile.
    Ties are handled with the 'average' method.

    This is the primary normalization method for CETR because:
    - Non-parametric: no distribution assumptions (important for N=10)
    - Robust to outliers: Alberta's extreme values don't distort other provinces
    - Intuitive: 'province scores 80' → higher risk than 80% of provinces
    - Recommended by OECD Handbook for small-N comparisons

    Parameters
    ----------
    series : pd.Series
        Raw metric values. NaN values are excluded from ranking.

    Returns
    -------
    pd.Series
        Percentile ranks in [0, 100]. Same index as input.
        NaN inputs produce NaN outputs.
    """
    # rank(pct=True) returns [0, 1] — multiply by 100
    # method='average' handles ties by averaging their ranks
    return series.rank(pct=True, method="average", na_option="keep") * 100


def z_score(series: pd.Series, clip_sigma: float = 3.0) -> pd.Series:
    """
    Standardize to z-scores, then rescale to [0, 100].

    Z-scores measure how many standard deviations each value is from
    the mean. Outliers beyond ±clip_sigma are clipped before rescaling.

    Used only in sensitivity analysis to compare with percentile_rank.
    Not the primary method because N=10 is too small for reliable
    normality assumptions.

    Parameters
    ----------
    series : pd.Series
    clip_sigma : float
        Clip z-scores beyond this many standard deviations (default: 3.0).

    Returns
    -------
    pd.Series
        Rescaled z-scores in [0, 100].
    """
    mu = series.mean()
    sigma = series.std()

    if sigma == 0 or pd.isna(sigma):
        log.warning("z_score: standard deviation is 0 — all values identical. Returning 50.")
        return pd.Series(50.0, index=series.index)

    z = (series - mu) / sigma
    z_clipped = z.clip(-clip_sigma, clip_sigma)

    # Map [-clip_sigma, +clip_sigma] → [0, 100]
    rescaled = ((z_clipped + clip_sigma) / (2 * clip_sigma)) * 100
    return rescaled


def min_max(series: pd.Series) -> pd.Series:
    """
    Normalize to [0, 100] using min-max scaling.

    min_max(x) = (x - min) / (max - min) × 100

    Note: sensitive to outliers because the min and max anchor the scale.
    Alberta's extreme stranded asset values compress all other provinces
    toward 0. Use only in sensitivity analysis.

    Parameters
    ----------
    series : pd.Series

    Returns
    -------
    pd.Series
        Min-max normalized values in [0, 100].
    """
    lo = series.min()
    hi = series.max()

    if hi == lo:
        log.warning("min_max: all values identical. Returning 50.")
        return pd.Series(50.0, index=series.index)

    return ((series - lo) / (hi - lo)) * 100


def entropy_weights(df: pd.DataFrame) -> dict[str, float]:
    """
    Compute data-driven entropy weights for each column (metric).

    Shannon information entropy theory: a metric with high variance
    across provinces (high information content) gets more weight than
    one where all provinces score similarly (low information, high entropy).

    Formula:
        p_ij = x_ij / sum_j(x_ij)          # proportion
        E_j  = -k * sum_i(p_ij * ln(p_ij)) # entropy for metric j
        d_j  = 1 - E_j                      # redundancy (information content)
        w_j  = d_j / sum_j(d_j)            # normalized weight

    where k = 1/ln(N), N = number of provinces.

    Parameters
    ----------
    df : pd.DataFrame
        Rows = provinces, columns = raw metric values.
        All values must be positive (this is enforced by adding a small constant).

    Returns
    -------
    dict[str, float]
        Column name → entropy weight. Weights sum to 1.0.

    References
    ----------
    Shannon (1948); Zou et al. (2006); applied to energy transition indices
    in the literature per docs/references.md.
    """
    n = len(df)
    if n < 2:
        raise ValueError("Need at least 2 provinces to compute entropy weights")

    # Normalization constant: ensures entropy is in [0, 1]
    k = 1.0 / np.log(n)

    weights = {}
    for col in df.columns:
        values = df[col].dropna()
        if len(values) < 2:
            weights[col] = 1.0 / len(df.columns)
            continue

        # Ensure all values strictly positive before computing proportions.
        # We use raw values (not subtract-min) so that genuinely uniform
        # distributions (e.g. [5, 5, 5, 6, 5]) get high entropy → low weight.
        # Subtracting the min would amplify tiny differences and invert the result.
        v = values.clip(lower=0) + 1e-10  # shift to strictly positive

        # Compute proportions (probability distribution over provinces)
        p = v / v.sum()

        # Shannon entropy
        entropy = -k * (p * np.log(p + 1e-300)).sum()

        # Redundancy (information content)
        redundancy = 1.0 - entropy
        weights[col] = max(redundancy, 0.0)

    # Normalize weights to sum to 1
    total = sum(weights.values())
    if total == 0:
        # Degenerate case: all metrics have identical values
        n_cols = len(df.columns)
        return {col: 1.0 / n_cols for col in df.columns}

    return {col: w / total for col, w in weights.items()}


def normalize_all_methods(series: pd.Series) -> pd.DataFrame:
    """
    Apply all normalization methods to a single series.
    Returns a DataFrame with columns: percentile_rank, z_score, min_max.
    Used in sensitivity analysis.

    Parameters
    ----------
    series : pd.Series

    Returns
    -------
    pd.DataFrame
        Three columns of normalized scores, same index as series.
    """
    return pd.DataFrame({
        "percentile_rank": percentile_rank(series),
        "z_score":         z_score(series),
        "min_max":         min_max(series),
    }, index=series.index)
