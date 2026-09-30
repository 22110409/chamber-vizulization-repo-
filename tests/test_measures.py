import numpy as np
import pandas as pd
import pytest

from chamberstudio.measures import (ExpressionError, add_column, aggregate, evaluate, parse, previous_period,
                                    quick_calc, sort_table, top_n_other, total, yoy)


# ---------------------------------------------------------------- aggregation
@pytest.mark.parametrize("agg,china", [("sum", 1600), ("mean", 800), ("count", 2), ("min", 600), ("max", 1000),
                                       ("median", 800), ("nunique", 2)])
def test_aggregations(df, agg, china):
    t = aggregate(df, "Country", "Value", agg)
    assert t.set_index("Country").loc["China", "value"] == china


def test_count_rows_without_value(df):
    t = aggregate(df, ["Sector"], None)
    assert t.set_index("Sector")["value"].to_dict() == {"Industry": 3, "Services": 1, "Trade": 3}


def test_total(df):
    assert total(df, "Value") == 2950
    assert total(df, None) == 7


def test_top_n_other(df):
    t = aggregate(df, "Country", "Value")
    got = top_n_other(t, "Country", 2).set_index("Country")["value"].to_dict()
    assert got == {"China": 1600, "Iraq": 800, "Other": 550}


def test_top_n_other_with_a_legend(df):
    t = aggregate(df, ["Country", "Sector"], "Value")
    got = top_n_other(t, "Country", 1)
    assert set(got["Country"]) == {"China", "Other"}
    assert got["value"].sum() == pytest.approx(t["value"].sum())


def test_sort(df):
    t = aggregate(df, "Country", "Value")
    assert list(sort_table(t, "Country", "desc")["Country"]) == ["China", "Iraq", "Egypt", "Jordan"]
    assert list(sort_table(t, "Country", "asc")["Country"]) == ["Jordan", "Egypt", "Iraq", "China"]


# ---------------------------------------------------------------- quick calculations
@pytest.fixture
def yearly():
    return pd.DataFrame({"Year": [2023, 2024, 2025, 2023, 2024, 2025],
                         "Flow": ["Imports"] * 3 + ["Exports"] * 3,
                         "value": [100.0, 110.0, 99.0, 50.0, 60.0, 90.0]})


def test_pct_of_total(yearly):
    t = quick_calc(yearly, "pct_total")
    assert t["value"].sum() == pytest.approx(100)
    t = quick_calc(yearly, "pct_total", within="Flow")
    assert t.groupby("Flow")["value"].sum().tolist() == pytest.approx([100, 100])


def test_running_total_rank_moving_average(yearly):
    imp = yearly[yearly.Flow == "Imports"]
    assert quick_calc(imp, "running")["value"].tolist() == [100, 210, 309]
    assert quick_calc(imp, "rank")["value"].tolist() == [2, 1, 3]
    assert quick_calc(imp, "moving_avg", window=2)["value"].tolist() == [100, 105, 104.5]


def test_year_over_year(yearly):
    t = quick_calc(yearly, "yoy_pct", time_col="Year", within="Flow").set_index(["Flow", "Year"])["value"]
    assert np.isnan(t[("Imports", 2023)])
    assert t[("Imports", 2024)] == pytest.approx(10.0)
    assert t[("Imports", 2025)] == pytest.approx(-10.0)
    assert t[("Exports", 2025)] == pytest.approx(50.0)
    t = quick_calc(yearly, "yoy", time_col="Year", within="Flow").set_index(["Flow", "Year"])["value"]
    assert t[("Exports", 2024)] == 10


def test_year_over_year_monthly():
    t = pd.DataFrame({"Month": ["2024-01", "2024-02", "2025-01", "2025-02"], "value": [10.0, 20.0, 15.0, 10.0]})
    got = yoy(t, "Month").set_index("Month")["change_pct"]
    assert got["2025-01"] == pytest.approx(50) and got["2025-02"] == pytest.approx(-50)


def test_previous_period():
    assert previous_period(2025) == 2024
    assert previous_period("2025 Q3") == "2024 Q3"
    assert previous_period(pd.Timestamp("2025-03-01")) == pd.Timestamp("2024-03-01")


# ---------------------------------------------------------------- safe formulas
@pytest.fixture
def trade():
    return pd.DataFrame({"Exports": [10.0, 20.0, 0.0], "Imports": [4.0, 25.0, 0.0],
                         "Value (JD million)": [1500.0, 2500.0, None]})


@pytest.mark.parametrize("formula,expected", [
    ("Exports - Imports", [6, -5, 0]),
    ("[Value (JD million)] / 1000", [1.5, 2.5, np.nan]),
    ("`Value (JD million)` * 2", [3000, 5000, np.nan]),
    ("round(Exports / Imports, 2)", [2.5, 0.8, np.nan]),          # 0/0 -> empty, not an error
    ("abs(Exports - Imports) + 1", [7, 6, 1]),
    ("max(Exports, Imports)", [10, 25, 0]),
    ("coalesce([Value (JD million)], 0)", [1500, 2500, 0]),
    ("-exports ** 2", [-100, -400, 0]),                            # names are case-insensitive
    ("100", [100, 100, 100]),
])
def test_formulas(trade, formula, expected):
    np.testing.assert_allclose(evaluate(formula, trade).to_numpy(), expected, equal_nan=True)


def test_add_column(trade):
    out = add_column(trade, "Balance", "Exports - Imports")
    assert out["Balance"].tolist() == [6, -5, 0]
    assert "Balance" not in trade.columns


@pytest.mark.parametrize("formula,reason", [
    ("__import__('os').system('dir')", "allowed functions"),
    ("Exports.__class__", "not allowed"),
    ("open('x')", "allowed functions"),
    ("Exports if Imports else 0", "not allowed"),
    ("Exports > Imports", "not allowed"),
    ("'text'", "only numbers"),
    ("lambda: 1", "not allowed"),
    ("[Exprts] + 1", "unknown column 'Exprts'"),
    ("Exports +", "cannot read"),
    ("round(Exports, ndigits=2)", "takes"),
    ("True + 1", "only numbers"),
    ("Exports[0]", "unknown column '0'"),     # [..] is the column syntax
    ("", "empty"),
    ("1 + " * 300 + "1", "longer than"),
])
def test_formulas_that_are_refused(trade, formula, reason):
    with pytest.raises(ExpressionError, match=reason):
        evaluate(formula, trade)


def test_parse_does_not_run_anything(trade):
    tree, mapping = parse("[Value (JD million)] - Exports", trade.columns)
    assert set(mapping.values()) == {"Value (JD million)", "Exports"}
