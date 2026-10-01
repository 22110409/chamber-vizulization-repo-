import matplotlib

matplotlib.use("Agg")

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from chamberstudio import data  # noqa: E402
from chamberstudio import filters as F  # noqa: E402
from chamberstudio import visuals as V  # noqa: E402
from conftest import SAMPLE  # noqa: E402


@pytest.fixture(scope="module")
def trade():
    raw = data.load_file(SAMPLE)["Trade"]
    schema = data.default_schema(raw)
    schema["Value (JD thousand)"]["label"] = "Value"
    df = data.apply_schema(raw, schema)
    kinds = {v["label"]: v["kind"] for v in schema.values()}
    return df, kinds


def test_bar_top_n_and_other_keep_the_total(trade):
    df, kinds = trade
    table, meta = V.prepare(df, V.VisualSpec("bar", "Country", "Value", top_n=5), kinds)
    assert len(table) == 6 and "Other" in table[meta.category].tolist()
    assert table["value"].sum() == pytest.approx(df["Value"].sum())
    body = table[table[meta.category] != "Other"]["value"].tolist()
    assert body == sorted(body, reverse=True)
    assert meta.country


def test_time_drill_down_and_up(trade):
    df, kinds = trade
    spec = V.VisualSpec("bar", "Month", "Value")
    assert V.level_of(df, spec, kinds) == "month"            # 36 months: shown month by month
    V.set_level(spec, "year")
    table, meta = V.prepare(df, spec, kinds)
    assert table[meta.category].tolist() == ["2023", "2024", "2025"]   # time stays in order
    V.drill_down(df, spec, kinds, "2025")
    table, meta = V.prepare(df, spec, kinds)
    assert meta.level == "quarter" and table[meta.category].tolist() == ["2025 Q1", "2025 Q2", "2025 Q3", "2025 Q4"]
    V.drill_down(df, spec, kinds, "2025 Q2")
    table, meta = V.prepare(df, spec, kinds)
    assert table[meta.category].tolist() == ["2025-04", "2025-05", "2025-06"]
    expected = df[(df.Month >= "2025-04-01") & (df.Month <= "2025-06-01")]["Value"].sum()
    assert table["value"].sum() == pytest.approx(expected)
    assert V.breadcrumb(spec, kinds) == "All › 2025 › 2025 Q2  (Month)"
    V.drill_up(df, spec, kinds)
    V.drill_up(df, spec, kinds)
    assert spec.level == "year" and spec.path == []


def test_drill_after_jumping_to_a_level(trade):
    df, kinds = trade
    spec = V.set_level(V.VisualSpec("bar", "Month", "Value"), "month")
    V.drill_down(df, spec, kinds, "2024-03")
    table, meta = V.prepare(df, spec, kinds)
    assert meta.level == "date" and table[meta.category].tolist() == ["2024-03-01"]


def test_region_drill_down(trade):
    df, kinds = trade
    spec = V.set_level(V.VisualSpec("bar", "Country", "Value"), "region")
    table, meta = V.prepare(df, spec, kinds)
    assert {"GCC", "Levant", "Asia", "EU", "Americas"} <= set(table[meta.category])
    V.drill_down(df, spec, kinds, "GCC")
    table, meta = V.prepare(df, spec, kinds)
    assert set(table[meta.category]) == {"Saudi Arabia", "United Arab Emirates", "Kuwait", "Qatar", "Oman", "Bahrain"}


def test_legend_and_quick_calcs(trade):
    df, kinds = trade
    spec = V.set_level(V.VisualSpec("line", "Month", "Value", legend="Flow", quick="yoy_pct"), "year")
    table, meta = V.prepare(df, spec, kinds)
    assert set(table["Flow"]) == {"Imports", "Exports", "Re-exports"}
    imp = table[table.Flow == "Imports"].set_index(meta.category)
    manual = df[df.Flow == "Imports"].groupby(df.Month.dt.year)["Value"].sum()
    assert imp.loc["2025", "value"] == pytest.approx((manual[2025] / manual[2024] - 1) * 100)
    share = V.prepare(df, V.VisualSpec("donut", "Flow", "Value", quick="pct_total"), kinds)[0]
    assert share["value"].sum() == pytest.approx(100)


def test_visual_filters_only_touch_that_visual(trade):
    df, kinds = trade
    spec = V.VisualSpec("bar", "Country", "Value", filters=F.Group("and", [F.CategoryFilter("Flow", ["Exports"])]))
    table, meta = V.prepare(df, spec, kinds)
    assert table["value"].sum() == pytest.approx(df[df.Flow == "Exports"]["Value"].sum())
    assert meta.rows == (df.Flow == "Exports").sum()


def test_kpi_compares_the_same_months(trade):
    df, kinds = trade
    table, _ = V.prepare(df, V.VisualSpec("kpi", "Month", "Value"), kinds)
    row = table.iloc[0]
    assert row["period"] == "2025" and row["prev_period"] == "2024"
    assert row["value"] == pytest.approx(df[df.Month.dt.year == 2025]["Value"].sum())
    assert row["previous"] == pytest.approx(df[df.Month.dt.year == 2024]["Value"].sum())


def test_scatter(trade):
    df, kinds = trade
    table, meta = V.prepare(df, V.VisualSpec("scatter", "Country", "Value", x_value="Weight (tonnes)",
                                             size="Value"), kinds)
    assert {"value", "x_value", "size"} <= set(table.columns) and len(table) == df.Country.nunique()


@pytest.mark.parametrize("kind", list(V.TYPES))
def test_every_type_draws_in_plotly(trade, kind):
    df, kinds = trade
    spec = V.VisualSpec(kind, "Country", "Value", legend="Flow" if kind in V.MULTI else None,
                        x_value="Weight (tonnes)" if kind == "scatter" else None, top_n=8)
    if kind == "kpi":
        spec.category = "Month"
    table, meta = V.prepare(df, spec, kinds)
    if kind == "table":
        assert len(table)
        return
    fig = V.to_plotly(table, spec, meta, "navy_gold")
    assert fig.data, kind


@pytest.mark.parametrize("kind", [k for k in V.TYPES if k != "table"])
def test_every_type_exports_with_chamberviz(trade, kind):
    df, kinds = trade
    spec = V.VisualSpec(kind, "Country", "Value", legend="Flow" if kind in V.MULTI else None,
                        x_value="Weight (tonnes)" if kind == "scatter" else None, top_n=8)
    if kind == "kpi":
        spec.category = "Month"
    table, meta = V.prepare(df, spec, kinds)
    chart = V.to_chamberviz(table, spec, meta, design="report_slate", logo=None, dpi=40)
    assert chart.to_bytes()[:4] == b"\x89PNG"
    chart.close()


def test_suggest_for_me(trade):
    df, kinds = trade
    specs = V.suggest(df.head(3000))
    assert specs and all(s.type in V.TYPES for s in specs)
    for s in specs:
        for col in (s.category, s.value, s.legend, s.x_value):
            assert col is None or col in df.columns


def test_round_trip():
    spec = V.VisualSpec("grouped", "Month", "Value", legend="Flow", top_n=5, level="quarter",
                        path=[["year", "2025"]], filters=F.Group("or", [F.CategoryFilter("Country", ["China"])]))
    again = V.VisualSpec.from_dict(spec.to_dict())
    assert again.to_dict() == spec.to_dict()
