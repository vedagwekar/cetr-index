"""Canada Energy Regulator ingestion (Canada's Energy Future data).

TODO:
- Download electricity generation by fuel and province from the CER data portal.
- Compute fossil share = (coal + natural gas + oil) / total generation.
- Return a tidy table keyed on ``fossil_generation_share``.
"""

import pandas as pd


def load() -> pd.DataFrame:
    raise NotImplementedError("CER ingestion not built yet")
