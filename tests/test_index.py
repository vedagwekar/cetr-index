import pandas as pd

from cetr.index import compute_index
from cetr.normalize import min_max


def test_min_max_range():
    s = min_max(pd.Series([2.0, 4.0, 6.0]))
    assert s.tolist() == [0.0, 0.5, 1.0]


def test_min_max_flipped():
    s = min_max(pd.Series([2.0, 4.0, 6.0]), higher_is_riskier=False)
    assert s.tolist() == [1.0, 0.5, 0.0]


def test_min_max_constant():
    assert min_max(pd.Series([3.0, 3.0])).tolist() == [0.5, 0.5]


def test_compute_index_orders_by_risk():
    rows = []
    for region, v in [("AB", 10.0), ("ON", 2.0), ("QC", 1.0)]:
        for ind in [
            "fossil_employment_share",
            "energy_gdp_share",
            "emissions_intensity",
            "fossil_generation_share",
        ]:
            rows.append({"region": region, "year": 2024, "indicator": ind, "value": v})
    out = compute_index(pd.DataFrame(rows), 2024)
    assert out.index[0] == "AB"
    assert out.loc["AB", "cetr_score"] == 100
    assert out.loc["QC", "cetr_score"] == 0
