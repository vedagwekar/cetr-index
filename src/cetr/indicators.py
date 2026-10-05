"""Indicator and pillar definitions for the CETR Index.

Every indicator is oriented so that a HIGHER raw value means HIGHER
transition risk. If a source measures the opposite (e.g. renewable share),
set ``higher_is_riskier=False`` and it will be flipped during normalization.
"""

from dataclasses import dataclass

REGIONS = [
    "NL", "PE", "NS", "NB", "QC", "ON", "MB", "SK", "AB", "BC", "YT", "NT", "NU",
]


@dataclass(frozen=True)
class Indicator:
    key: str
    name: str
    pillar: str
    source: str
    weight: float  # weight within its pillar
    higher_is_riskier: bool = True


INDICATORS = [
    Indicator(
        key="fossil_employment_share",
        name="Share of employment in oil, gas, and coal",
        pillar="labour",
        source="statcan",
        weight=1.0,
    ),
    Indicator(
        key="energy_gdp_share",
        name="Energy-sector share of GDP",
        pillar="economic",
        source="statcan",
        weight=1.0,
    ),
    Indicator(
        key="emissions_intensity",
        name="GHG emissions per dollar of GDP",
        pillar="emissions",
        source="statcan",
        weight=1.0,
    ),
    Indicator(
        key="fossil_generation_share",
        name="Fossil-fuel share of electricity generation",
        pillar="energy_system",
        source="cer",
        weight=1.0,
    ),
]

# Weight of each pillar in the composite score. Must sum to 1.
PILLAR_WEIGHTS = {
    "labour": 0.25,
    "economic": 0.25,
    "emissions": 0.25,
    "energy_system": 0.25,
}
