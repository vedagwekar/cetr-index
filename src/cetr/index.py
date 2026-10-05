"""Combine normalized indicators into pillar scores and a composite index."""

import pandas as pd

from .indicators import INDICATORS, PILLAR_WEIGHTS
from .normalize import min_max


def compute_index(tidy: pd.DataFrame, year: int) -> pd.DataFrame:
    """Compute CETR scores for one year.

    Args:
        tidy: long table with columns ``region, year, indicator, value``.
        year: the year to score.

    Returns:
        One row per region with a column per pillar plus ``cetr_score`` (0-100).
    """
    wide = (
        tidy[tidy["year"] == year]
        .pivot(index="region", columns="indicator", values="value")
    )

    pillar_scores = {}
    for pillar in PILLAR_WEIGHTS:
        members = [i for i in INDICATORS if i.pillar == pillar and i.key in wide]
        if not members:
            continue
        total_w = sum(i.weight for i in members)
        pillar_scores[pillar] = sum(
            min_max(wide[i.key], i.higher_is_riskier) * i.weight for i in members
        ) / total_w

    scores = pd.DataFrame(pillar_scores)
    used_w = sum(PILLAR_WEIGHTS[p] for p in scores.columns)
    scores["cetr_score"] = 100 * sum(
        scores[p] * PILLAR_WEIGHTS[p] for p in pillar_scores
    ) / used_w
    return scores.sort_values("cetr_score", ascending=False)
