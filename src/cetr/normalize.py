"""Scaling methods that put indicators on a common 0-1 scale."""

import pandas as pd


def min_max(values: pd.Series, higher_is_riskier: bool = True) -> pd.Series:
    """Scale values to 0-1, where 1 is the riskiest region.

    If every value is identical, all regions get 0.5 (no relative difference).
    """
    lo, hi = values.min(), values.max()
    if hi == lo:
        return pd.Series(0.5, index=values.index)
    scaled = (values - lo) / (hi - lo)
    return scaled if higher_is_riskier else 1 - scaled
