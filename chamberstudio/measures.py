"""Measures: aggregations, quick calculations and safe calculated columns.

    table = aggregate(df, by=["Country"], value="Value", agg="sum")
    table = top_n_other(table, "Country", 5)
    table["share"] = pct_of_total(table)
    df = add_column(df, "Balance", "Exports - Imports")        # safe: no eval

Calculated columns accept + - * / // % **, numbers, column names (use [Name with spaces] or
`Name with spaces`) and the functions abs, round, sqrt, log, log10, exp, min, max, coalesce.
Anything else (attributes, imports, strings, comparisons, lambdas ...) is refused.
"""
from __future__ import annotations

import ast
import re

import numpy as np
import pandas as pd

AGGS = {"sum": "Sum", "mean": "Average", "count": "Count", "nunique": "Distinct count", "min": "Min",
        "max": "Max", "median": "Median"}
QUICK_CALCS = {"none": "None", "pct_total": "% of total", "yoy": "Change on last year",
               "yoy_pct": "% change on last year", "running": "Running total", "rank": "Rank",
               "moving_avg": "Moving average"}
VALUE = "value"


# ---------------------------------------------------------------- aggregation
def aggregate(df: pd.DataFrame, by, value: str | None = None, agg: str = "sum") -> pd.DataFrame:
    """Group by one or more columns and aggregate one value column -> columns [*by, 'value'].
    value=None (or agg='count' without a value) counts rows."""
    by = [by] if isinstance(by, str) else [b for b in (by or []) if b]
    if agg not in AGGS:
        raise ValueError(f"unknown aggregation {agg!r}")
    if not by:
        if value is None:
            return pd.DataFrame({VALUE: [float(len(df))]})
        s = df[value]
        return pd.DataFrame({VALUE: [float(getattr(s, agg)()) if len(s) else np.nan]})
    g = df.groupby(by, observed=True, sort=True, dropna=True)
    if value is None:
        out = g.size().rename(VALUE)
    else:
        out = g[value].agg(agg).rename(VALUE)
    return out.reset_index()


def total(df: pd.DataFrame, value: str | None, agg: str = "sum") -> float:
    """One number (a KPI card)."""
    return float(aggregate(df, [], value, agg)[VALUE].iloc[0])


def top_n_other(table: pd.DataFrame, category: str, n: int, value: str = VALUE, other: str = "Other",
                bottom: bool = False, keep_other: bool = True) -> pd.DataFrame:
    """Keep the n largest categories (by their total, across any legend) and add the rest up as
    'Other'."""
    if not n or table[category].nunique() <= n:
        return table
    totals = table.groupby(category, observed=True)[value].sum().sort_values(ascending=bottom)
    keep = set(totals.head(int(n)).index)
    inside = table[table[category].isin(keep)]
    if not keep_other:
        return inside.reset_index(drop=True)
    rest = table[~table[category].isin(keep)]
    rest_cols = [c for c in table.columns if c not in (category, value)]
    if rest_cols:
        rest = rest.groupby(rest_cols, observed=True, dropna=False)[value].sum().reset_index()
    else:
        rest = pd.DataFrame({value: [rest[value].sum()]})
    rest[category] = other
    out = pd.concat([inside.astype({category: "object"}), rest[table.columns]], ignore_index=True)
    return out


def sort_table(table: pd.DataFrame, category: str, order: str = "desc", value: str = VALUE) -> pd.DataFrame:
    """desc / asc by value (totals across a legend), 'label' A-Z, or 'none' (keep the data order)."""
    if order in ("desc", "asc"):
        totals = table.groupby(category, observed=True, sort=False)[value].sum()
        ranked = totals.sort_values(ascending=order == "asc").index
        pos = {k: i for i, k in enumerate(ranked)}
        # plain values: mapping a categorical would keep its alphabetical order
        return table.sort_values(category, key=lambda s: s.astype(object).map(pos),
                                 kind="stable").reset_index(drop=True)
    if order == "label":
        return table.sort_values(category, kind="stable").reset_index(drop=True)
    return table


# ---------------------------------------------------------------- quick calculations
def _grouped(table, within):
    within = [w for w in ([within] if isinstance(within, str) else (within or [])) if w]
    return table.groupby(within, observed=True, sort=False) if within else None


def pct_of_total(table: pd.DataFrame, value: str = VALUE, within=None) -> pd.Series:
    """Share of the total, in % (within=a legend column: share inside each legend value)."""
    g = _grouped(table, within)
    tot = g[value].transform("sum") if g is not None else table[value].sum()
    return table[value] / tot * 100


def running_total(table: pd.DataFrame, value: str = VALUE, within=None) -> pd.Series:
    g = _grouped(table, within)
    return g[value].cumsum() if g is not None else table[value].cumsum()


def rank(table: pd.DataFrame, value: str = VALUE, within=None, ascending: bool = False) -> pd.Series:
    g = _grouped(table, within)
    r = (g[value] if g is not None else table[value]).rank(method="min", ascending=ascending)
    return r.astype("Int64")


def moving_average(table: pd.DataFrame, value: str = VALUE, window: int = 3, within=None) -> pd.Series:
    g = _grouped(table, within)
    if g is not None:
        return g[value].transform(lambda s: s.rolling(window, min_periods=1).mean())
    return table[value].rolling(window, min_periods=1).mean()


def previous_period(key):
    """The same period one year earlier: 2025 -> 2024, '2025-03' -> '2024-03', '2025 Q1' -> '2024 Q1'."""
    if isinstance(key, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(key) - pd.DateOffset(years=1)
    if isinstance(key, (int, np.integer)) or (isinstance(key, float) and float(key).is_integer()):
        return int(key) - 1
    text = str(key)
    m = re.match(r"^(\d{4})(.*)$", text)
    if m:
        return f"{int(m.group(1)) - 1}{m.group(2)}"
    return None


def yoy(table: pd.DataFrame, time_col: str, value: str = VALUE, within=None) -> pd.DataFrame:
    """Adds 'previous', 'change' and 'change_pct' (vs the same period of the year before)."""
    within = [w for w in ([within] if isinstance(within, str) else (within or [])) if w]
    t = table.copy()
    t["_key"] = t[time_col].map(lambda k: str(k) if not isinstance(k, pd.Timestamp) else k)
    prev = t[[*within, "_key", value]].rename(columns={value: "previous"})
    t["_prev_key"] = t[time_col].map(previous_period).map(lambda k: str(k) if not isinstance(k, pd.Timestamp) else k)
    out = t.merge(prev.rename(columns={"_key": "_prev_key"}), on=[*within, "_prev_key"], how="left")
    out["change"] = out[value] - out["previous"]
    with np.errstate(divide="ignore", invalid="ignore"):
        out["change_pct"] = np.where(out["previous"].abs() > 0, out["change"] / out["previous"].abs() * 100, np.nan)
    return out.drop(columns=["_key", "_prev_key"])


def quick_calc(table: pd.DataFrame, calc: str, time_col: str | None = None, within=None,
               window: int = 3) -> pd.DataFrame:
    """Replace 'value' with a quick calculation of it (the original stays in 'base')."""
    if calc in (None, "none"):
        return table
    t = table.copy()
    t["base"] = t[VALUE]
    if calc == "pct_total":
        t[VALUE] = pct_of_total(t, within=within)
    elif calc == "running":
        t[VALUE] = running_total(t, within=within)
    elif calc == "rank":
        t[VALUE] = rank(t, within=within).astype(float)
    elif calc == "moving_avg":
        t[VALUE] = moving_average(t, window=window, within=within)
    elif calc in ("yoy", "yoy_pct"):
        if not time_col:
            raise ValueError("change on last year needs a year / month / quarter column")
        t = yoy(t, time_col, within=within)
        t[VALUE] = t["change"] if calc == "yoy" else t["change_pct"]
    else:
        raise ValueError(f"unknown quick calculation {calc!r}")
    return t


# ---------------------------------------------------------------- safe calculated columns
class ExpressionError(ValueError):
    pass


_BINOPS = {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply, ast.Div: np.divide,
           ast.FloorDiv: np.floor_divide, ast.Mod: np.mod, ast.Pow: np.power}
_UNARY = {ast.USub: np.negative, ast.UAdd: np.positive}
_FUNCS = {
    "abs": (1, 1, lambda x: np.abs(x)),
    "round": (1, 2, lambda x, d=0: np.round(x, int(d))),
    "sqrt": (1, 1, lambda x: np.sqrt(x)),
    "log": (1, 1, lambda x: np.log(x)),
    "log10": (1, 1, lambda x: np.log10(x)),
    "exp": (1, 1, lambda x: np.exp(x)),
    "min": (2, 2, lambda a, b: np.minimum(a, b)),
    "max": (2, 2, lambda a, b: np.maximum(a, b)),
    "coalesce": (2, 2, lambda a, b: pd.Series(a).fillna(b) if isinstance(a, pd.Series) else (b if pd.isna(a) else a)),
}
MAX_LENGTH = 400


def _prepare(text: str, columns) -> tuple[str, dict]:
    """[Col name] / `Col name` -> placeholder names; returns (python text, {placeholder: column})."""
    if not isinstance(text, str) or not text.strip():
        raise ExpressionError("the formula is empty")
    if len(text) > MAX_LENGTH:
        raise ExpressionError(f"the formula is longer than {MAX_LENGTH} characters")
    cols = [str(c) for c in columns]
    mapping = {}

    def sub(m):
        name = m.group(1) or m.group(2)
        col = _find_column(name, cols)
        key = f"__c{len(mapping)}"
        mapping[key] = col
        return key

    return re.sub(r"\[([^\[\]]+)\]|`([^`]+)`", sub, text), mapping


def _find_column(name: str, cols: list[str]) -> str:
    if name in cols:
        return name
    low = [c for c in cols if c.lower() == name.strip().lower()]
    if len(low) == 1:
        return low[0]
    raise ExpressionError(f"unknown column '{name}' (columns: {', '.join(cols)})")


def parse(text: str, columns) -> tuple[ast.Expression, dict]:
    """Check a formula without running it. Raises ExpressionError with a readable reason."""
    py, mapping = _prepare(text, columns)
    try:
        tree = ast.parse(py, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"cannot read the formula: {exc.msg}") from None
    cols = [str(c) for c in columns]
    for node in ast.walk(tree):
        if isinstance(node, (ast.Expression, ast.Load)) or type(node) in _BINOPS or type(node) in _UNARY:
            continue
        if isinstance(node, ast.BinOp):
            if type(node.op) not in _BINOPS:
                raise ExpressionError("only + - * / // % ** are allowed")
        elif isinstance(node, ast.UnaryOp):
            if type(node.op) not in _UNARY:
                raise ExpressionError("only - and + signs are allowed")
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise ExpressionError("only numbers can be written in a formula")
        elif isinstance(node, ast.Name):
            if node.id not in mapping and node.id not in _FUNCS:
                mapping[node.id] = _find_column(node.id, cols)
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS:
                raise ExpressionError(f"allowed functions: {', '.join(_FUNCS)}")
            lo, hi, _ = _FUNCS[node.func.id]
            if node.keywords or not lo <= len(node.args) <= hi:
                raise ExpressionError(f"{node.func.id}() takes {lo if lo == hi else f'{lo}-{hi}'} value(s)")
        else:
            raise ExpressionError(f"'{type(node).__name__}' is not allowed in a formula")
    return tree, mapping


def evaluate(text: str, df: pd.DataFrame) -> pd.Series:
    """The formula's value for every row (division by zero gives an empty value)."""
    tree, mapping = parse(text, df.columns)

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.BinOp):
            return _BINOPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp):
            return _UNARY[type(node.op)](ev(node.operand))
        if isinstance(node, ast.Constant):
            return float(node.value)
        if isinstance(node, ast.Name):
            return pd.to_numeric(df[mapping[node.id]], errors="coerce").astype("float64")
        if isinstance(node, ast.Call):
            return _FUNCS[node.func.id][2](*[ev(a) for a in node.args])
        raise ExpressionError("not allowed")  # parse() already refused anything else

    with np.errstate(all="ignore"):
        out = ev(tree)
    if not isinstance(out, pd.Series):
        out = pd.Series(np.full(len(df), float(out)), index=df.index)
    return out.replace([np.inf, -np.inf], np.nan)


def add_column(df: pd.DataFrame, name: str, formula: str) -> pd.DataFrame:
    name = str(name).strip()
    if not name:
        raise ExpressionError("give the new column a name")
    return df.assign(**{name: evaluate(formula, df)})
