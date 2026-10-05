# Methodology Decision Log

Every non-obvious methodological choice is documented here with the
alternative that was rejected and the reasoning. This file becomes
Section 3 of the white paper.

Last updated: 2026-05-24

---

## D-001: Normalization method — percentile rank vs z-score vs min-max

**Date:** 2026-05-24  
**Decision:** Percentile rank (primary method)  
**Rationale:**  
The OECD Handbook on Constructing Composite Indicators (2008, p.27) recommends
percentile rank for small-N comparisons where the normality assumption cannot
be verified. With N=10 provinces, z-scores are unreliable. Additionally,
Alberta's fossil fuel GDP (22%+ of GDP) is an extreme outlier — under min-max
normalization, this compresses all other provinces toward 0, making meaningful
differentiation impossible among the 9 non-Alberta provinces.

Percentile rank is also intuitive for public communication: "Alberta scores 80"
means Alberta has higher transition risk than 80% of provinces.

**Alternative rejected — z-score:** Requires normality assumption; N=10 is too
small for reliable inference. Alberta's outlier values would dominate the scale.

**Alternative rejected — min-max:** Sensitive to outliers. Alberta's extreme
stranded asset exposure would compress BC, ON, QC scores into an
indistinguishable range near 0.

**Reference:** OECD/JRC (2008), Handbook on Constructing Composite Indicators,
Chapter 3 (Normalisation), pp. 27-33.

---

## D-002: Weighting approach — equal vs differential vs data-driven

**Date:** 2026-05-24  
**Decision:** Differential expert weights (0.25/0.25/0.20/0.15/0.15)  
**Rationale:**  
Equal weights (0.20 each) were considered and rejected because they imply
all five components capture risk with equal relevance. Carbon intensity and
stranded asset risk are the two most directly tied to financial exposure
(carbon pricing, asset devaluation) and are supported by the largest body of
academic literature (TCFD framework, Carbon Tracker). Grid reliability,
energy poverty, and workforce exposure are important but less directly tied
to near-term financial risk.

The two primary components (carbon intensity + stranded asset risk) sum to 0.50.
The three secondary components sum to 0.50. This reflects a 50/50 split between
"current physical risk" and "structural socioeconomic risk."

**Alternative considered — data-driven entropy weights:** Entropy weights are
used in the sensitivity analysis (see Section 5) and produce very similar
rankings (Spearman ρ > 0.92). The expert-assigned weights are preferred for
the primary index because they are interpretable and defensible to non-technical
audiences.

**Reference:** Singh et al. (2019), The energy transitions index; WEF ETI
methodology documentation (2024).

---

## D-003: Unit of analysis — province vs census division vs municipal

**Date:** 2026-05-24  
**Decision:** Province  
**Rationale:**  
Energy policy in Canada is primarily a provincial jurisdiction (Constitution Act
1867, Section 92A). Statistics Canada's most reliable and consistently updated
economic data (GDP, employment, household spending) is available at the
provincial level with consistent time series back to 2010.

Census division data would allow more granular analysis (e.g. differentiating
Fort McMurray from Edmonton within Alberta) but key metrics (particularly
grid reliability SAIDI and energy poverty) are only published at provincial
aggregation.

**Future work:** Municipal-level data for the 10 largest Canadian cities is
planned for v2. This would allow scoring Calgary, Edmonton, Toronto, etc.
separately.

---

## D-004: Exclusion of territories (YT, NT, NU)

**Date:** 2026-05-24  
**Decision:** Exclude territories  
**Rationale:**  
The three territories have fundamentally different energy systems — diesel
microgrids serving remote communities, with no connection to the North American
grid. The SAIDI concept does not apply in the same way. GDP and employment data
are available but sparse, with high suppression rates due to small populations.

Including the territories would distort the provincial index because their
very small denominators (population, GDP) produce extreme ratio values.

**Future work:** A separate territorial energy transition assessment using
different metrics (diesel dependency %, renewable penetration, fuel trucking
costs) is planned as a companion product.

---

## D-005: Grid reliability metric — SAIDI without major events

**Date:** 2026-05-24  
**Decision:** SAIDI without major events (SAIDI-WME)  
**Rationale:**  
The CEA reports two SAIDI figures: total SAIDI (including major storm events)
and SAIDI without major events (SAIDI-WME). For cross-provincial comparison,
SAIDI-WME is more appropriate because it reflects structural grid quality
rather than one-time storm exposure. Major event frequency varies by geography
(BC is more storm-prone than Saskatchewan) and would confound the metric's
purpose of measuring grid reliability under electrification.

**Alternative rejected — total SAIDI:** Would penalize provinces with more
severe weather (Atlantic provinces) for factors not related to energy
transition readiness.

---

## D-006: Energy poverty threshold — 6% of household income

**Date:** 2026-05-24  
**Decision:** 6% threshold  
**Rationale:**  
The 6% threshold is the standard adopted by NRCan, Efficiency Canada, and the
Canadian Energy Poverty Taskforce. It aligns with international standard
(the UK government uses a similar 10% threshold; the 6% Canadian figure
is adjusted for income distribution differences).

**Reference:** Efficiency Canada, "Affordable Energy for All Canadians" (2020);
NRCan Energy Poverty Task Force recommendations (2021).

---

## D-007: Data sourcing for grid reliability — manual vs automated

**Date:** 2026-05-24  
**Decision:** Manual CSV maintained at data/raw/cea_reliability_manual.csv  
**Rationale:**  
The CEA Reliability Report is the only authoritative source for provincial
SAIDI in Canada. It is published as a PDF with no machine-readable equivalent.
PDF extraction using pdfplumber is implemented as a secondary option
(see pipeline/clean/grid_reliability.py) but the table format changes
annually, making automated extraction unreliable.

The manual CSV approach is more robust for v1: update it once per year when
the new CEA report is released (~Q1). The pipeline logs a clear warning if
the data is stale (> 18 months old).

**Migration path:** If CEA publishes a machine-readable version (expected as
part of Canada's open data initiatives), migrate to automated fetching.

---

## D-008: Handling suppressed Stats Canada values

**Date:** 2026-05-24  
**Decision:** Use provincial totals where sub-industry data is suppressed  
**Rationale:**  
Stats Canada suppresses sub-industry GDP and employment values for small
provinces (PE, NL, sometimes NB) when the value could identify specific firms.
For suppressed fossil fuel employment in PE (where the value is genuinely
near-zero), the suppression itself is informative — it implies a small value.

**Implementation:** When sub-industry values sum to less than 70% of the
total provincial fossil fuel aggregate (suggesting significant suppression),
a note is added to the output CSV and the value is flagged as an estimate.

---

## Planned decisions (v2)

- D-009: Adding renewable energy investment rate as a 6th component
- D-010: Adding carbon price exposure as a weighted factor
- D-011: Incorporating Indigenous land overlay for stranded asset risk
- D-012: Methodology for territorial index (separate from provincial)
