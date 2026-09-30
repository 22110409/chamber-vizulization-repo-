import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SAMPLE = ROOT / "examples" / "sample_trade_dashboard.xlsx"


@pytest.fixture
def df():
    """Seven rows covering every kind of column (text columns stored as categories, like the app)."""
    d = pd.DataFrame({
        "Country": ["China", "Egypt", "China", "Iraq", "Egypt", "Jordan", None],
        "Sector": ["Industry", "Trade", "Trade", "Industry", "Services", "Industry", "Trade"],
        "Value": [1000.0, 300.0, 600.0, 800.0, 200.0, 50.0, None],
        "Date": pd.to_datetime(["2024-01-15", "2024-06-01", "2025-01-10", "2025-03-01", "2025-12-01",
                                "2023-05-05", "2025-11-30"]),
        "Year": pd.array([2024, 2024, 2025, 2025, 2025, 2023, 2025], dtype="Int64"),
        "Note": ["Crude oil", "olive OIL", "cars", "oil seeds", "phones", "", None],
    })
    for c in ("Country", "Sector", "Note"):
        d[c] = d[c].astype("category")
    return d
