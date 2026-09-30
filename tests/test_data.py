import time

import pandas as pd
import pytest

from chamberstudio import data, regions
from chamberstudio.filters import CategoryFilter, DateFilter, Group, NumberFilter, TextFilter, apply_filters
from chamberstudio.measures import aggregate
from conftest import SAMPLE


@pytest.fixture(scope="module")
def book():
    return data.load_file(SAMPLE)


def test_sample_sheets_and_kinds(book):
    assert list(book) == ["Trade", "Countries", "التجارة"]
    kinds = data.detect_kinds(book["Trade"])
    assert kinds == {"Month": "date", "Country": "country", "Commodity": "category", "Flow": "category",
                     "Value (JD thousand)": "number", "Weight (tonnes)": "number"}
    assert data.detect_kinds(book["التجارة"])["الدولة"] == "country"


def test_schema_change_kind_rename_hide(book):
    raw = book["Trade"]
    schema = data.default_schema(raw)
    schema["Value (JD thousand)"]["label"] = "Value"
    schema["Weight (tonnes)"]["hidden"] = True
    schema["Flow"]["kind"] = "text"
    df = data.apply_schema(raw, schema)
    assert list(df.columns) == ["Month", "Country", "Commodity", "Flow", "Value"]
    assert isinstance(df["Country"].dtype, pd.CategoricalDtype)
    assert pd.api.types.is_datetime64_any_dtype(df["Month"])
    assert data.kinds_of(df)["Country"] == "country"


def test_convert_between_kinds():
    s = pd.Series(["1,234", "56", "x", None])
    assert data.convert(s, "number").tolist()[:2] == [1234.0, 56.0]
    years = pd.Series([2024, 2025])
    assert data.convert(years, "date").dt.year.tolist() == [2024, 2025]
    dates = pd.Series(pd.to_datetime(["2024-03-01", "2025-07-09"]))
    assert data.convert(dates, "year").tolist() == [2024, 2025]


def test_join_countries(book):
    joined, info = data.join(book["Trade"], book["Countries"], "Country")
    assert "Population (million)" in joined.columns and "Arabic name" in joined.columns
    assert info["matched"] == info["rows"] == len(book["Trade"])


def test_join_reports_unmatched():
    left = pd.DataFrame({"Country": ["China", "Atlantis"], "v": [1, 2]})
    right = pd.DataFrame({"Country": ["china"], "Pop": [1410]})
    joined, info = data.join(left, right, "Country")
    assert info == {"matched": 1, "rows": 2}
    assert joined["Pop"].tolist()[0] == 1410


def test_time_parts(book):
    s = book["Trade"]["Month"]
    assert data.time_parts(s, "quarter").iloc[0] == "2023 Q1"
    assert data.time_parts(s, "month").iloc[0] == "2023-01"
    assert int(data.time_parts(s, "year").iloc[0]) == 2023


def test_regions():
    assert regions.region_of("السعودية") == "GCC"
    assert regions.region_of("UAE") == "GCC"
    assert regions.region_of("Syria") == "Levant"
    assert regions.region_of("مصر") == "Other Arab countries"
    assert regions.region_of("Germany") == "EU"
    assert regions.region_of("China") == "Asia"
    assert regions.region_of("Brazil") == "Americas"
    assert regions.region_of("Nigeria") == "Africa"
    assert regions.region_of("United Kingdom") == "Other"
    assert regions.region_of("Atlantis") == "Other"
    assert regions.group_regions("Arab world") == ["GCC", "Levant", "Other Arab countries"]
    assert regions.region_label("GCC", "ar") == "دول الخليج العربي"
    col = regions.region_column(pd.Series(["China", "Egypt", "China"]))
    assert col.tolist() == ["Asia", "Other Arab countries", "Asia"]


# ---------------------------------------------------------------- speed
@pytest.fixture(scope="module")
def big():
    import sys
    sys.path.insert(0, str(SAMPLE.parent))
    from make_dashboard_sample import big as make_big
    raw = make_big(500_000)
    return data.apply_schema(raw, data.default_schema(raw.head(5000)))


def test_500k_rows_filter_under_two_seconds(big):
    assert len(big) == 500_000
    spec = Group("and", [
        Group("or", [
            Group("and", [CategoryFilter("Country", ["China", "Egypt", "Iraq"]),
                          NumberFilter("Value (JD thousand)", ">", 500)]),
            CategoryFilter("Commodity", ["Vehicles"]),
        ]),
        DateFilter("Month", "last_12_months"),
        TextFilter("Commodity", "contains", "e"),
        CategoryFilter("Country", top_n=10, top_by="Value (JD thousand)"),
    ])
    start = time.perf_counter()
    out = apply_filters(big, spec)
    table = aggregate(out, ["Country", "Flow"], "Value (JD thousand)")
    seconds = time.perf_counter() - start
    assert len(out) > 0 and len(table) > 0
    assert seconds < 2.0, f"{seconds:.2f}s"
