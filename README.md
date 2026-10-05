# CETR Index: Canadian Energy Transition Risk Index

**How exposed is each Canadian province and territory to the global shift away from fossil fuels?**

The CETR Index is an open-source Python pipeline that pulls public data from **Statistics Canada** and the **Canada Energy Regulator (CER)**, turns it into a consistent set of risk indicators, and combines them into a single score from **0 (low risk)** to **100 (high risk)** for each of Canada's 13 provinces and territories.

> **Project status: early development.** The project structure, indicator definitions, scoring method, and tests are in place. Automated data ingestion from Statistics Canada and the CER is being built next. See the [Roadmap](#roadmap).

---

## Table of contents

- [Why this project exists](#why-this-project-exists)
- [What "transition risk" means here](#what-transition-risk-means-here)
- [The four pillars](#the-four-pillars)
- [How the score is calculated](#how-the-score-is-calculated)
- [Worked example](#worked-example)
- [Data sources](#data-sources)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Using the code](#using-the-code)
- [Design decisions](#design-decisions)
- [Limitations](#limitations)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## Why this project exists

Canada is one of the world's largest oil and gas producers, but the economic weight of that industry is spread very unevenly across the country. In some provinces, fossil fuels support a large share of jobs, government revenue, and electricity. In others, they barely register.

As countries cut emissions and demand for fossil fuels changes, those regional differences turn into very different levels of exposure. A policy that is a minor adjustment for one province can be a major economic shock for another.

Public discussion of this tends to rely on single numbers (emissions totals, oil production, or job counts) looked at one at a time. The CETR Index brings several of these measures together using a transparent, reproducible method, so the provinces can be compared on the same scale and the reasoning behind each score can be checked.

The goals are:

- **Comparability:** put every region on the same 0-100 scale.
- **Transparency:** every indicator, weight, and formula is in plain Python and documented here.
- **Reproducibility:** anyone can re-run the pipeline on the latest public data and get the same result.

---

## What "transition risk" means here

In climate finance, **transition risk** is the risk that comes from the *move to a low-carbon economy*: changes in policy, technology, markets, and demand. It is different from **physical risk**, which comes from climate impacts themselves (floods, wildfires, heat).

This index measures **transition risk only**. A high score means a region's economy, workforce, and energy system currently depend heavily on fossil fuels, so it has more to adjust as that dependence declines.

A high score is **not** a judgment of a province's policies, and it is not a forecast. It is a measure of present-day exposure.

---

## The four pillars

The index is built from four **pillars**, each answering a different question. Each pillar contains one or more **indicators**.

### 1. Labour exposure
*How many workers depend on fossil-fuel industries?*

| Indicator | Definition | Source |
|---|---|---|
| `fossil_employment_share` | Share of total employment in oil and gas extraction, coal mining, and support activities | Statistics Canada, Labour Force Survey |

Jobs are the most direct way the transition reaches households. A region where many people work in extraction faces retraining, relocation, and income pressure if demand drops.

### 2. Economic dependence
*How much of the economy comes from the energy sector?*

| Indicator | Definition | Source |
|---|---|---|
| `energy_gdp_share` | Energy sector's share of provincial or territorial GDP | Statistics Canada, GDP by industry |

A large energy share of GDP means the region's overall output, and often its government revenue through royalties, is tied to fossil-fuel prices and volumes.

### 3. Emissions intensity
*How carbon-heavy is the economy?*

| Indicator | Definition | Source |
|---|---|---|
| `emissions_intensity` | Greenhouse gas emissions per dollar of GDP | Statistics Canada / Environment and Climate Change Canada |

Carbon pricing and emissions regulations cost more where each dollar of output produces more emissions. This pillar captures exposure to policy, not just to markets.

### 4. Energy system
*How much of the electricity supply comes from fossil fuels?*

| Indicator | Definition | Source |
|---|---|---|
| `fossil_generation_share` | Share of electricity generated from coal, natural gas, and oil | Canada Energy Regulator |

Regions that generate power mostly from fossil fuels need to rebuild part of their grid. Regions running mostly on hydro or nuclear are already largely through this step.

All indicators are defined in [`src/cetr/indicators.py`](src/cetr/indicators.py).

---

## How the score is calculated

The pipeline runs in four stages.

```
  Statistics Canada ─┐
                     ├─► 1. Ingest ─► 2. Clean ─► 3. Normalize ─► 4. Weight & combine ─► CETR score
  Canada Energy      │     (raw)       (tidy)      (0 to 1)         (pillars, composite)    (0 to 100)
  Regulator ─────────┘
```

### Stage 1: Ingest
Each data source has its own module in `src/cetr/ingest/` that downloads the raw tables and saves them to `data/raw/`.

### Stage 2: Clean
Every source is converted into the same **tidy** format, one row per measurement:

| region | year | indicator | value |
|---|---|---|---|
| AB | 2024 | fossil_employment_share | ... |
| ON | 2024 | fossil_employment_share | ... |

Using one shared format means the scoring code never has to know where a number came from.

### Stage 3: Normalize
Indicators are measured in different units (percentages, tonnes per dollar, and so on), so they are rescaled to a common 0-1 range using **min-max normalization**:

```
normalized = (value - lowest value) / (highest value - lowest value)
```

The riskiest region on an indicator gets **1**, the least risky gets **0**, and everyone else falls in between. If an indicator is defined so that a higher number means *lower* risk (for example, renewable share), it is flipped: `1 - normalized`. If every region has the same value, all get 0.5, since there is no difference to measure.

### Stage 4: Weight and combine
1. **Pillar score:** the weighted average of the normalized indicators in that pillar.
2. **Composite score:** the weighted average of the pillar scores, multiplied by 100.

```
pillar score  = Σ (indicator weight × normalized indicator) / Σ indicator weights
CETR score    = 100 × Σ (pillar weight × pillar score) / Σ pillar weights
```

By default all four pillars are weighted equally at 25%. The weights live in `PILLAR_WEIGHTS` in `indicators.py` and can be changed to test how sensitive the rankings are to these choices.

If an indicator is missing, the pipeline uses the pillars it does have and rescales their weights, rather than failing or silently treating the gap as zero.

---

## Worked example

Using made-up numbers for three regions and one indicator:

| Region | Fossil employment share | Normalized |
|---|---|---|
| A | 6.0% | (6.0 - 0.5) / (6.0 - 0.5) = **1.00** |
| B | 2.0% | (2.0 - 0.5) / (6.0 - 0.5) = **0.27** |
| C | 0.5% | (0.5 - 0.5) / (6.0 - 0.5) = **0.00** |

If Region B scored 0.27, 0.40, 0.60, and 0.20 across the four pillars, with equal weights:

```
CETR score = 100 × (0.25×0.27 + 0.25×0.40 + 0.25×0.60 + 0.25×0.20) = 36.75
```

These figures are illustrative only and are not real provincial data.

---

## Data sources

| Source | What it provides | Access |
|---|---|---|
| [Statistics Canada Web Data Service](https://www.statcan.gc.ca/en/developers/wds) | Employment by industry, GDP by industry, greenhouse gas emissions | Free public API |
| [Canada Energy Regulator: Canada's Energy Future](https://www.cer-rec.gc.ca/en/data-analysis/canada-energy-future/) | Electricity generation by fuel type and province | Free public data downloads |

Statistics Canada data is used under the [Statistics Canada Open Licence](https://www.statcan.gc.ca/en/reference/licence). CER data is used under the [Open Government Licence – Canada](https://open.canada.ca/en/open-government-licence-canada).

Raw and processed data files are **not** committed to this repository. They are downloaded fresh when the pipeline runs, so results always reflect the latest releases.

---

## Project structure

```
cetr-index/
├── src/cetr/
│   ├── __init__.py
│   ├── indicators.py      # Regions, indicator definitions, pillar weights
│   ├── normalize.py       # Min-max scaling
│   ├── index.py           # Pillar and composite scoring
│   └── ingest/
│       ├── statcan.py     # Statistics Canada ingestion (in progress)
│       └── cer.py         # CER ingestion (in progress)
├── data/
│   ├── raw/               # Downloaded source tables (git-ignored)
│   └── processed/         # Cleaned outputs (git-ignored)
├── notebooks/             # Exploration and charts
├── tests/
│   └── test_index.py      # Unit tests for normalization and scoring
├── pyproject.toml
├── LICENSE
└── README.md
```

---

## Getting started

**Requirements:** Python 3.10 or newer.

```bash
git clone https://github.com/vedagwekar/cetr-index.git
cd cetr-index

python -m venv .venv
source .venv/bin/activate        # On Windows: .venv\Scripts\activate

pip install -e ".[dev]"
pytest
```

All tests should pass.

---

## Using the code

Once ingestion is complete, the pipeline will run with a single command. Until then, the scoring engine can be used directly with any tidy table:

```python
import pandas as pd
from cetr.index import compute_index

data = pd.DataFrame([
    {"region": "AB", "year": 2024, "indicator": "fossil_employment_share", "value": 6.0},
    {"region": "ON", "year": 2024, "indicator": "fossil_employment_share", "value": 0.4},
    {"region": "QC", "year": 2024, "indicator": "fossil_employment_share", "value": 0.2},
    # ...add rows for the other indicators
])

scores = compute_index(data, year=2024)
print(scores)
```

The result has one row per region, a column for each pillar (0-1), and a `cetr_score` column (0-100), sorted from highest to lowest risk.

### Adding an indicator

1. Add an `Indicator(...)` entry to `INDICATORS` in `indicators.py`, choosing its pillar and weight.
2. Make sure the matching ingest module outputs rows with that `indicator` key.
3. Add a test.

No changes to the scoring code are needed.

---

## Design decisions

**Why min-max normalization?** It is simple, easy to explain, and keeps the result on an intuitive 0-1 scale. The trade-off is that it is *relative*: scores show how regions compare to each other, not how they compare to a fixed target. Z-score and fixed-threshold scaling are planned as alternatives.

**Why equal pillar weights?** Without a strong reason to rank one dimension above another, equal weights are the most neutral starting point and are standard practice in composite indices such as the UN Human Development Index. Making the weights configurable lets users test other assumptions.

**Why a tidy long format?** It lets every data source, however different its raw layout, feed into the same scoring code. Adding a source means writing one ingest module, not changing the index logic.

**Why include the territories?** Yukon, the Northwest Territories, and Nunavut face distinct energy challenges (for example, diesel-dependent remote communities) that are often left out of national comparisons.

---

## Limitations

- **Relative, not absolute.** Because of min-max scaling, a score of 0 means "lowest among Canadian regions," not "no risk."
- **Snapshot in time.** The index measures current exposure. It does not model future policy, prices, or a region's capacity to adapt.
- **Data gaps.** Some Statistics Canada tables suppress figures for small regions, especially the territories. These gaps will be documented as ingestion is built.
- **Missing dimensions.** Fiscal dependence on royalties, household energy costs, and adaptive capacity (education, economic diversity) are not yet included.
- **Weights are a choice.** Different reasonable weightings can change the rankings. Sensitivity analysis is on the roadmap.

---

## Roadmap

- [x] Project structure and packaging
- [x] Indicator and pillar definitions
- [x] Normalization and composite scoring
- [x] Unit tests for the scoring engine
- [ ] Statistics Canada ingestion (employment, GDP, emissions)
- [ ] CER ingestion (electricity generation by fuel)
- [ ] Mapping of source region names to standard codes
- [ ] Command-line entry point to run the full pipeline
- [ ] Time series: scores for every available year
- [ ] Sensitivity analysis on weights and normalization methods
- [ ] Additional indicators: royalty dependence, household energy costs, adaptive capacity
- [ ] Interactive map and charts

---

## Contributing

Suggestions, bug reports, and pull requests are welcome. If you think an indicator is missing, mis-specified, or weighted unfairly, please open an issue explaining your reasoning and any data sources.

---

## License

The code is released under the [MIT License](LICENSE). Data remains subject to the licences of its original publishers.

*Built by [Ved Agwekar](https://github.com/vedagwekar).*
