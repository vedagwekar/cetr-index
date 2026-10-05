"""Statistics Canada ingestion (Web Data Service).

TODO:
- Pick table IDs for employment by industry, GDP by industry, and GHG emissions.
- Download full tables via the WDS ``getFullTableDownloadCSV`` endpoint into data/raw/.
- Map StatCan GEO names to the two-letter codes in ``cetr.indicators.REGIONS``.
"""

import pandas as pd


def load() -> pd.DataFrame:
    raise NotImplementedError("Statistics Canada ingestion not built yet")
