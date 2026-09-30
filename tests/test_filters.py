import pytest

from chamberstudio.filters import (BLANK, CategoryFilter, DateFilter, Group, NumberFilter, TextFilter, apply_filters,
                                   columns_used, delete_preset, describe, dumps, from_dict, is_active, list_presets,
                                   load_preset, loads, mask, save_preset, to_dict)


def rows(df, spec):
    return list(apply_filters(df, spec).index)


# ---------------------------------------------------------------- category
def test_category_select_and_exclude(df):
    assert rows(df, CategoryFilter("Country", ["China", "Egypt"])) == [0, 1, 2, 4]
    # exclude keeps the other countries and the blank one
    assert rows(df, CategoryFilter("Country", ["China", "Egypt"], exclude=True)) == [3, 5, 6]


def test_category_nothing_selected_keeps_everything(df):
    assert len(apply_filters(df, CategoryFilter("Country", []))) == len(df)
    assert not is_active(CategoryFilter("Country", []))


def test_category_blank_value(df):
    assert rows(df, CategoryFilter("Country", [BLANK])) == [6]


def test_category_on_a_year_column_matches_text_and_numbers(df):
    assert rows(df, CategoryFilter("Year", ["2023", 2024])) == [0, 1, 5]


def test_top_n_by_measure(df):
    # totals: China 1600, Iraq 800, Egypt 500, Jordan 50
    assert set(apply_filters(df, CategoryFilter("Country", top_n=2, top_by="Value"))["Country"]) == {"China", "Iraq"}
    bottom = CategoryFilter("Country", top_n=1, top_by="Value", bottom=True)
    assert set(apply_filters(df, bottom)["Country"]) == {"Jordan"}


def test_top_n_ranks_inside_the_other_and_filters(df):
    # only Trade rows: China 600, Egypt 300 -> top 1 is China (not Iraq, which only has Industry)
    spec = Group("and", [CategoryFilter("Country", top_n=1, top_by="Value"), CategoryFilter("Sector", ["Trade"])])
    assert rows(df, spec) == [2]


def test_top_n_by_row_count(df):
    got = apply_filters(df, CategoryFilter("Country", top_n=2))
    assert set(got["Country"]) == {"China", "Egypt"}


# ---------------------------------------------------------------- number
@pytest.mark.parametrize("op,value,value2,expected", [
    (">", 500, None, [0, 2, 3]), (">=", 600, None, [0, 2, 3]), ("<", 300, None, [4, 5]), ("<=", 300, None, [1, 4, 5]),
    ("=", 800, None, [3]), ("!=", 800, None, [0, 1, 2, 4, 5]), ("between", 200, 600, [1, 2, 4]),
    ("between", None, 100, [5]), ("empty", None, None, [6]), ("not_empty", None, None, [0, 1, 2, 3, 4, 5]),
])
def test_number_operators(df, op, value, value2, expected):
    assert rows(df, NumberFilter("Value", op, value, value2)) == expected


def test_number_without_value_is_inactive(df):
    assert len(apply_filters(df, NumberFilter("Value", ">"))) == len(df)


# ---------------------------------------------------------------- dates (latest date in the data: 2025-12-01)
@pytest.mark.parametrize("spec,expected", [
    (DateFilter("Date", "this_year"), [2, 3, 4, 6]),
    (DateFilter("Date", "last_year"), [0, 1]),
    (DateFilter("Date", "ytd"), [2, 3, 4, 6]),
    (DateFilter("Date", "last_12_months"), [2, 3, 4, 6]),
    (DateFilter("Date", "range", start="2024-01-01", end="2024-12-31"), [0, 1]),
    (DateFilter("Date", "range", start="2025-06-01"), [4, 6]),
    (DateFilter("Date", "pick", years=[2024, 2025], quarters=[1]), [0, 2, 3]),
    (DateFilter("Date", "pick", months=[12, 11]), [4, 6]),
])
def test_date_presets(df, spec, expected):
    assert rows(df, spec) == expected


def test_ytd_stops_at_the_anchor(df):
    d = df.copy()
    d.loc[6, "Date"] = d["Date"].max() + __import__("pandas").Timedelta(days=5)  # latest now 2025-12-06
    assert 6 in rows(d, DateFilter("Date", "ytd"))


def test_year_column_presets(df):
    assert rows(df, DateFilter("Year", "this_year")) == [2, 3, 4, 6]
    assert rows(df, DateFilter("Year", "last_year")) == [0, 1]
    assert rows(df, DateFilter("Year", "range", start="2023", end="2024")) == [0, 1, 5]
    assert rows(df, DateFilter("Year", "pick", years=[2023])) == [5]


def test_today_anchor(df):
    # relative to today (2026 or later): nothing in the sample is "this year"
    assert rows(df, DateFilter("Date", "this_year", anchor="today")) == []


# ---------------------------------------------------------------- text
@pytest.mark.parametrize("op,value,expected", [
    ("contains", "oil", [0, 1, 3]), ("contains", "OIL", [0, 1, 3]), ("starts", "oil", [3]), ("ends", "oil", [0, 1]),
    ("equals", "cars", [2]), ("not_contains", "oil", [2, 4, 5]),
])
def test_text_operators(df, op, value, expected):
    assert rows(df, TextFilter("Note", op, value)) == expected


def test_text_case_sensitive(df):
    assert rows(df, TextFilter("Note", "contains", "OIL", case_sensitive=True)) == [1]


def test_text_on_plain_strings(df):
    d = df.assign(Note=df["Note"].astype("object"))
    assert rows(d, TextFilter("Note", "contains", "oil")) == [0, 1, 3]


# ---------------------------------------------------------------- groups
def test_or_group_of_and_group(df):
    # (Country in [China, Egypt] AND Value > 500) OR Sector = Services
    spec = Group("or", [
        Group("and", [CategoryFilter("Country", ["China", "Egypt"]), NumberFilter("Value", ">", 500)]),
        CategoryFilter("Sector", ["Services"]),
    ])
    assert rows(df, spec) == [0, 2, 4]
    assert describe(spec) == "(Country: China, Egypt AND Value > 500) OR Sector: Services"


def test_not_group(df):
    assert rows(df, Group("and", [CategoryFilter("Sector", ["Industry"])], negate=True)) == [1, 2, 4, 6]


def test_empty_group_keeps_everything(df):
    assert len(apply_filters(df, Group("or", []))) == len(df)


def test_page_and_visual_filters_combine(df):
    page = Group("and", [DateFilter("Date", "this_year")])
    visual = Group("and", [CategoryFilter("Sector", ["Industry"])])
    assert rows(df.loc[:], page) == [2, 3, 4, 6]
    assert list(apply_filters(df, page, visual).index) == [3]


def test_unknown_column_is_a_clear_error(df):
    with pytest.raises(KeyError, match="Countryy"):
        mask(df, CategoryFilter("Countryy", ["China"]))


# ---------------------------------------------------------------- JSON, chips, presets
def test_json_round_trip(df):
    spec = Group("or", [
        Group("and", [CategoryFilter("Country", ["China"], top_n=3, top_by="Value"), NumberFilter("Value", "between", 1, 9)]),
        DateFilter("Date", "pick", years=[2025], quarters=[1, 2]),
        TextFilter("Note", "starts", "oil"),
    ], negate=True)
    again = loads(dumps(spec))
    assert again == spec
    assert to_dict(from_dict(to_dict(spec))) == to_dict(spec)
    assert list(mask(df, again)) == list(mask(df, spec))


def test_chips(df):
    assert describe(CategoryFilter("Country", ["A", "B", "C"])) == "Country: 3 selected"
    assert describe(CategoryFilter("Country", ["A"], exclude=True)) == "Country: not A"
    assert describe(CategoryFilter("Country", top_n=5, top_by="Value")) == "Country: top 5 by Value"
    assert describe(NumberFilter("Value", "between", 100, 1500.5)) == "Value between 100 and 1,500.50"
    assert describe(DateFilter("Date", "last_12_months")) == "Date: last 12 months"
    assert describe(TextFilter("Note", "contains", "oil")) == "Note contains “oil”"
    assert describe(CategoryFilter("Country", ["A", "B", "C"]), lang="ar") == "Country: 3 محدد"


def test_columns_used():
    spec = Group("or", [CategoryFilter("A", ["x"]), Group("and", [NumberFilter("B", ">", 1)])])
    assert columns_used(spec) == {"A", "B"}


def test_presets(tmp_path, df):
    spec = Group("and", [CategoryFilter("Country", ["Egypt"]), NumberFilter("Value", ">", 250)])
    save_preset("Egypt big / مصر", spec, folder=tmp_path)
    assert list_presets(tmp_path) == ["Egypt big  مصر"]
    assert load_preset("Egypt big  مصر", folder=tmp_path) == spec
    assert rows(df, load_preset("Egypt big  مصر", folder=tmp_path)) == [1]
    delete_preset("Egypt big  مصر", folder=tmp_path)
    assert list_presets(tmp_path) == []
