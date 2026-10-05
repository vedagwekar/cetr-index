# CETR Index: Canadian Energy Transition Risk Index

**How exposed is each Canadian province to the shift away from fossil fuels?**

The CETR Index is an open-source Python pipeline that pulls public data from **Statistics Canada**, the **Canada Energy Regulator (CER)**, and other public sources, turns it into five risk measures, and combines them into a single score from **0 (lowest risk)** to **100 (highest risk)** for each of Canada's ten provinces.

> **Project status: working pipeline, real-data integration in progress.** Ingestion, cleaning, scoring, sensitivity analysis, tests, and automation are built and run end to end. Several components currently fall back to hard-coded reference values when live source data isn't available, so **published scores are not yet final**. See [Current status](#current-status).

---

## Table of contents

- [Why this project exists](#why-this-project-exists)
- [What "transition risk" means here](#what-transition-risk-means-here)
- [The five components](#the-five-components)
- [How the score is calculated](#how-the-score-is-calculated)
- [Checking that the method is robust](#checking-that-the-method-is-robust)
- [Data sources](#data-sources)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Automation](#automation)
- [Testing](#testing)
- [Current status](#current-status)
- [Limitations](#limitations)
- [Roadmap](#roadmap)
- [Project history](#project-history)
- [Contributing](#contributing)
- [License](#license)

---

## Why this project exists

Canada is one of the world's largest oil and gas producers, but the economic weight of that industry is spread very unevenly. In some provinces, fossil fuels support a large share of GDP, jobs, and electricity. In others they barely register.

As countries cut emissions and fossil-fuel demand changes, those differences turn into very different levels of exposure. A carbon policy that is a minor adjustment for Quebec can be a major economic shock for Alberta.

Public discussion tends to rely on single numbers (emissions totals, oil production, job counts) looked at one at a time. Existing ESG and transition indices are mostly national or company-level, so they miss these provincial differences.

The CETR Index brings several measures together with a transparent, reproducible method so provinces can be compared on one scale, and so every assumption behind a score can be inspected and challenged.

The goals are:

- **Provincial detail:** Alberta's exposure is fundamentally different from Ontario's or Quebec's.
- **Transparency:** every weight, source, and normalization choice is recorded in [`methodology.json`](methodology.json) and justified in [`docs/decisions.md`](docs/decisions.md).
- **Reproducibility:** anyone can re-run the pipeline on the latest public data and get the same result.
- **Automation:** GitHub Actions is set up to refresh the data and recompute scores every quarter.

---

## What "transition risk" means here

In climate finance, **transition risk** is the risk that comes from the *move to a low-carbon economy*: changes in policy, technology, markets, and demand. It is different from **physical risk**, which comes from climate impacts themselves, such as floods, wildfires, and heat.

This index measures **transition risk only**. A high score means a province's economy, workforce, power grid, and households are currently more exposed to the costs of moving away from fossil fuels.

A high score is **not** a judgment of a province's policies, and it is not a forecast. It measures present-day exposure.

---

## The five components

Each component answers a different question about exposure. Weights are set in `methodology.json` and sum to exactly 1.

| Component | Question it answers | Measure | Weight |
|---|---|---|---|
| **Carbon intensity** | How carbon-heavy is the power grid? | tCO₂ per MWh of electricity generated | 25% |
| **Stranded asset risk** | How much of the economy depends on fossil fuels? | Fossil-fuel industries as % of provincial GDP | 25% |
| **Grid reliability** | Can the grid handle electrification? | SAIDI: average outage hours per customer per year | 20% |
| **Energy poverty** | How many households are vulnerable to higher energy costs? | % of households spending more than 6% of income on energy | 15% |
| **Workforce exposure** | How many workers depend on fossil fuels? | Fossil-fuel employment as % of total employment | 15% |

### Why these five

- **Carbon intensity** captures exposure to carbon pricing and regulation. A grid that runs on coal or gas must be rebuilt; one that runs on hydro or nuclear largely already has been.
- **Stranded asset risk** captures how much provincial output would lose value if fossil-fuel assets are written down by policy, new technology, or falling demand.
- **Grid reliability** matters because the transition depends on electrifying heating and transport. An unreliable grid makes that more expensive and harder to sell to the public.
- **Energy poverty** captures who pays. Carbon pricing and grid investment raise energy bills, and households already spending a large share of income on energy are hit hardest.
- **Workforce exposure** captures the human side: retraining costs, social disruption, and political resistance where many people work in fossil-fuel industries.

### Why the weights differ

Carbon intensity and stranded asset risk get the most weight because they are the most direct measures of transition exposure. Grid reliability, energy poverty, and workforce exposure shape how painful the transition is rather than how large it is, so they are weighted lower. The full reasoning, and the alternatives considered (equal weights and data-driven entropy weights), are in [`docs/decisions.md`](docs/decisions.md) under D-002.

---

## How the score is calculated

```
 Statistics Canada ─┐
 CER ───────────────┼─► 1. Ingest ─► 2. Clean ─► 3. Normalize ─► 4. Weight & combine ─► CETR score
 ECCC, CEA ─────────┘     (raw)       (tidy)      (0 to 1)          (weighted mean)       (0 to 100)
```

### 1. Ingest
`pipeline/ingest/` contains API clients for Statistics Canada and the CER, with retries and caching. Raw downloads go to `data/raw/`.

### 2. Clean
`pipeline/clean/` has one script per component. Each turns its raw tables into the same tidy shape:

| province | year | value |
|---|---|---|
| AB | 2023 | ... |

They also handle Statistics Canada's suppressed values, map industry codes to fossil-fuel sectors, and fall back to documented reference values when a source file is missing (see [Current status](#current-status)).

### 3. Normalize
The five components use different units, so each is converted to a 0-1 scale. The primary method is **percentile rank**: each province's position relative to the other nine.

Percentile rank was chosen over z-scores and min-max scaling because:
- With only 10 provinces, the normality assumption behind z-scores doesn't hold.
- Alberta is an extreme outlier on several components. Min-max scaling would let that single value squash every other province toward zero. Percentile rank is robust to it.

This follows the OECD *Handbook on Constructing Composite Indicators* (2008) guidance for small samples. See D-001 in `docs/decisions.md`.

### 4. Weight and combine
The normalized components are combined with a **weighted arithmetic mean** and scaled to 0-100:

```
CETR score = 100 × Σ (component weight × normalized component)
```

Provinces are then grouped into **High**, **Medium**, and **Low** risk bands.

---

## Checking that the method is robust

A composite index is only useful if its rankings don't flip on arbitrary choices. The pipeline therefore recomputes every score under **four normalization methods**:

1. Percentile rank (primary)
2. Z-score, clipped at ±3σ
3. Min-max
4. Entropy weighting (weights derived from the data's own variation)

It then calculates the **Spearman rank correlation** between every pair. The method is considered robust only if every pair correlates above **0.90**, meaning the provinces land in nearly the same order no matter which method is used. Results are written to `data/index/sensitivity_analysis.csv` and checked automatically by the test suite.

---

## Data sources

| Component | Source | Access |
|---|---|---|
| Stranded asset risk | Statistics Canada, Table 36-10-0402-01 (GDP by industry) | [Web Data Service API](https://www.statcan.gc.ca/en/developers/wds) |
| Workforce exposure | Statistics Canada, Table 14-10-0023-01 (Labour Force Survey) | Web Data Service API |
| Energy poverty | Statistics Canada, Table 11-10-0223-01 (household spending) | Web Data Service API |
| Carbon intensity | Environment and Climate Change Canada GHG Inventory + CER generation data | ECCC download + [CER open data](https://www.cer-rec.gc.ca/en/data-analysis/canada-energy-future/) |
| Grid reliability | Canadian Electricity Association annual reliability reports | Manual entry from published reports |

Statistics Canada data is used under the [Statistics Canada Open Licence](https://www.statcan.gc.ca/en/reference/licence). CER and ECCC data are used under the [Open Government Licence – Canada](https://open.canada.ca/en/open-government-licence-canada).

---

## Project structure

```
cetr-index/
├── methodology.json             # Weights, units, formulas, sources (single source of truth)
├── docs/
│   └── decisions.md             # Every methodological choice and the alternatives rejected
├── pipeline/
│   ├── constants.py             # Paths, province codes, industry mappings
│   ├── run_all.py               # Runs the whole pipeline, or one phase
│   ├── ingest/
│   │   ├── statcan_client.py    # Statistics Canada Web Data Service client
│   │   └── cer_client.py        # Canada Energy Regulator client
│   ├── clean/                   # One script per component
│   │   ├── carbon_intensity.py
│   │   ├── stranded_asset_risk.py
│   │   ├── grid_reliability.py
│   │   ├── energy_poverty.py
│   │   └── workforce_exposure.py
│   └── score/
│       ├── normalize.py         # Percentile rank, z-score, min-max, entropy weights
│       └── index_calculator.py  # Weighted scoring, risk bands, sensitivity analysis
├── tests/
│   ├── test_normalization.py    # Unit tests for each normalization method
│   └── test_index.py            # Methodology, data-quality, and economic sanity tests
├── data/
│   ├── raw/                     # Downloaded source files
│   ├── processed/               # Cleaned component tables
│   └── index/                   # Final scores and sensitivity analysis
├── .github/workflows/
│   ├── test.yml                 # Runs tests on every push
│   └── update_index.yml         # Quarterly data refresh
├── requirements.txt
└── LICENSE
```

---

## Getting started

**Requirements:** Python 3.11 or newer.

```bash
git clone https://github.com/vedagwekar/cetr-index.git
cd cetr-index

python -m venv venv
source venv/bin/activate          # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Run the full pipeline:

```bash
python -m pipeline.run_all
```

Or one phase at a time:

```bash
python -m pipeline.run_all --phase ingest   # download raw data
python -m pipeline.run_all --phase clean    # build the five component tables
python -m pipeline.run_all --phase score    # normalize, weight, and score
```

Outputs:

| File | Contents |
|---|---|
| `data/index/cetr_index_full.csv` | Every province, every year, every component, and the final score |
| `data/index/cetr_index_latest.json` | Latest year's scores and risk bands |
| `data/index/sensitivity_analysis.csv` | Scores under all four normalization methods |
| `data/index/run_log.json` | When the pipeline ran and what it produced |

To change weights or add a component, edit `methodology.json`. The scoring code reads its configuration from there.

---

## Automation

Two GitHub Actions workflows are included:

- **`test.yml`** runs the test suite on every push and pull request, and checks that the weights in `methodology.json` sum to 1.
- **`update_index.yml`** runs at 09:00 UTC on the first day of January, April, July, and October, lining up with Statistics Canada's quarterly releases. It downloads fresh data, rebuilds every component, recomputes scores, runs the full test suite, and commits the new data back to the repository. It can also be started by hand from the Actions tab.

---

## Testing

```bash
pytest tests/ -v
```

The tests are in three layers:

1. **Unit tests** (`test_normalization.py`) check each normalization method's math: output ranges, ordering, outlier handling, ties, and edge cases.
2. **Methodology tests** check that `methodology.json` is valid: all five components exist, weights are positive and sum to exactly 1, and all ten provinces are defined.
3. **Data and economic sanity tests** run once the pipeline has produced data. They check for missing provinces, negative or implausible values, and results that contradict well-known facts. For example, Alberta must rank highest on stranded asset risk, and Quebec, with a grid that runs almost entirely on hydro, must rank at or near the bottom on carbon intensity. A pipeline can be mathematically correct and still economically wrong; these tests catch that.

Tests that need pipeline output are skipped automatically when that output doesn't exist yet.

---

## Current status

What works:

- The full pipeline runs end to end with a single command.
- All four normalization methods, weighted scoring, risk bands, and the sensitivity analysis.
- Unit, methodology, and economic sanity tests.
- CI and quarterly-update workflows.

What's still in progress:

- **Fallback data.** When a live source can't be reached or parsed, the cleaning scripts use hard-coded reference values and log a clear warning. Until every component runs on live data, scores should be treated as **illustrative, not final**, which is why no results table is published here yet.
- **Carbon intensity** needs the ECCC GHG Inventory file, which isn't on a public API. This component doesn't produce output yet.
- **Grid reliability** comes from Canadian Electricity Association reports published as PDFs, so the data is entered by hand.
- **Monetary valuation** of stranded assets (a supplementary measure, not part of the main score) is defined in `methodology.json` but not yet generated.

---

## Limitations

- **Relative, not absolute.** Percentile ranks show where a province sits compared to the others, not against a fixed target. The lowest-scoring province is not "risk-free."
- **Ten provinces only.** Yukon, the Northwest Territories, and Nunavut are excluded because grid data is sparse and their energy systems (often diesel microgrids in remote communities) are too different to compare fairly. See D-004.
- **Snapshot of exposure.** The index measures where provinces are now. It doesn't model future policy, prices, or a province's capacity to adapt.
- **Weights are a judgment call.** Different reasonable weights can shift rankings. The sensitivity analysis tests normalization choices; weight sensitivity is planned.
- **Suppressed data.** Statistics Canada suppresses some figures for confidentiality, especially for smaller provinces. How these are handled is documented in D-008.

---

## Roadmap

- [x] Methodology design and decision log
- [x] Statistics Canada and CER ingestion clients
- [x] Cleaning scripts for all five components
- [x] Four normalization methods and weighted scoring
- [x] Sensitivity analysis with Spearman validation
- [x] Unit, methodology, and economic sanity tests
- [x] CI and quarterly-update workflows
- [ ] Replace fallback values with live data for every component
- [ ] Automate ECCC GHG Inventory ingestion for carbon intensity
- [ ] Generate the stranded-asset monetary valuation
- [ ] Weight sensitivity analysis
- [ ] Publish the first official results
- [ ] Add the territories (v2)
- [ ] Interactive map and charts

---

## Project history

### Why so much arrived at once

The commit history starts on **October 4, 2026**, and most of the codebase arrived in a few commits that day. That's not when the work was done.

The CETR Index was researched, designed, and built locally starting in **mid-2026**:

- **Research:** how composite indices are constructed and how transition risk is defined in climate finance.
- **Methodology:** choosing the five components, the weights, and the normalization method, and writing down the reasoning in `docs/decisions.md`.
- **Data mapping:** working out which Statistics Canada tables, CER datasets, and other sources could support each component.
- **Implementation:** the ingestion clients, cleaning scripts, scoring engine, tests, and workflows.

All of that lived on a local machine rather than in a Git repository. This repository was created to move the project into the open, and the existing code was imported in the first commits.

### Going forward

From here, development happens publicly in small, incremental commits, starting with replacing the fallback values with live data. The commit history from this point on is the real record of how the project evolves.

---

## Contributing

Suggestions, bug reports, and pull requests are welcome. If you think a component is missing, mis-measured, or weighted unfairly, please open an issue with your reasoning and any supporting data. Methodology changes should include an entry in `docs/decisions.md`.

---

## License

The code is released under the [MIT License](LICENSE). Data remains subject to the licences of its original publishers.

*Built by [Ved Agwekar](https://github.com/vedagwekar).*
