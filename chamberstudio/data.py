"""Loading data: files and sheets, column types, rename / hide, joins.

A column's settings are a plain dict (saved in the dashboard JSON):
    schema = {"Value": {"kind": "number", "label": "Value (JD)", "hidden": False}, ...}
Kinds: number, date, year, category, country, text.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import chamberviz as cv
from chamberviz.suggest import _to_number, profile

KINDS = ["number", "date", "year", "category", "country", "text"]
TEXT_KINDS = {"category", "country", "text"}
TIME_KINDS = {"date", "year"}


# ---------------------------------------------------------------- files
def load_file(path, sheet=None) -> dict[str, pd.DataFrame]:
    """Every sheet of an Excel/CSV file, cleaned by chamberviz (header row found, numbers stored
    as text converted, Total rows removed): {sheet name: DataFrame}."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    if sheet is not None:
        return {sheet: cv.read_excel(path, sheet=sheet)}
    return cv.read_excel(path)


# ---------------------------------------------------------------- column types
def detect_kinds(df: pd.DataFrame) -> dict[str, str]:
    """number / date / year / category / country, plus 'text' for free text (many long, unique values)."""
    kinds = {}
    for c in profile(df):
        kind = c.kind
        if kind == "category":
            s = df[c.name].dropna().astype(str)
            if len(s) and c.unique > 50 and c.unique > 0.5 * len(s) and s.str.len().mean() > 25:
                kind = "text"
        kinds[c.name] = kind
    return kinds


def default_schema(df: pd.DataFrame) -> dict:
    return {str(col): {"kind": kind, "label": str(col), "hidden": False} for col, kind in detect_kinds(df).items()}


def convert(s: pd.Series, kind: str) -> pd.Series:
    """Cast a column to a kind (values that do not fit become empty)."""
    if kind == "number":
        return _to_number(s).astype("float64")
    if kind == "date":
        if pd.api.types.is_datetime64_any_dtype(s):
            return s
        if pd.api.types.is_numeric_dtype(s):  # a year column turned into dates: 1 January
            return pd.to_datetime(s.astype("Int64").astype("string") + "-01-01", errors="coerce")
        return pd.to_datetime(s, errors="coerce")
    if kind == "year":
        if pd.api.types.is_datetime64_any_dtype(s):
            return s.dt.year.astype("Int64")
        return pd.to_numeric(_to_number(s), errors="coerce").round().astype("Int64")
    # category / country / text: strings stored as a pandas category (fast filters on big data)
    out = s.astype("string").str.strip()
    return out.astype("category")


def apply_schema(raw: pd.DataFrame, schema: dict | None) -> pd.DataFrame:
    """The data as the dashboard uses it: converted kinds, renamed columns, hidden ones removed."""
    schema = schema or default_schema(raw)
    out = {}
    for col in raw.columns:
        spec = schema.get(str(col)) or {"kind": detect_kinds(raw[[col]]).get(col, "category")}
        if spec.get("hidden"):
            continue
        label = spec.get("label") or str(col)
        out[label] = convert(raw[col], spec.get("kind", "category"))
    return pd.DataFrame(out, index=raw.index)


def kinds_of(df: pd.DataFrame) -> dict[str, str]:
    """Kinds of an already converted frame (by dtype, with countries recognised)."""
    out = {}
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            out[col] = "date"
        elif str(s.dtype) == "Int64" or (pd.api.types.is_integer_dtype(s) and s.dropna().between(1900, 2100).all()
                                         and "year" in str(col).lower()):
            out[col] = "year"
        elif pd.api.types.is_numeric_dtype(s):
            out[col] = "number"
        else:
            out[col] = "category"
    for c in profile(df[[c for c, k in out.items() if k == "category"]]) if any(k == "category" for k in out.values()) else []:
        if c.kind == "country":
            out[c.name] = "country"
    return out


# ---------------------------------------------------------------- joins
def join(left: pd.DataFrame, right: pd.DataFrame, left_on: str, right_on: str | None = None,
         how: str = "left") -> tuple[pd.DataFrame, dict]:
    """Add the right sheet's columns to the left one, matching on a common column
    (e.g. Country). Returns (joined frame, {"matched": rows with a match, "rows": total})."""
    right_on = right_on or left_on
    key_l = left[left_on].astype("string").str.strip().str.lower()
    r = right.copy()
    r["__key"] = r[right_on].astype("string").str.strip().str.lower()
    r = r.drop_duplicates("__key")
    extra = [c for c in r.columns if c not in (right_on, "__key")]
    rename = {c: (f"{c} ({right_on})" if c in left.columns else c) for c in extra}
    merged = left.assign(__key=key_l).merge(r[["__key", *extra]].rename(columns=rename), on="__key", how=how)
    matched = int(merged[list(rename.values())].notna().any(axis=1).sum()) if rename else 0
    return merged.drop(columns="__key"), {"matched": matched, "rows": len(merged)}


# ---------------------------------------------------------------- helpers
def time_parts(s: pd.Series, level: str) -> pd.Series:
    """Drill-down levels of a date or year column: year, quarter ('2025 Q1'), month ('2025-01')."""
    if not pd.api.types.is_datetime64_any_dtype(s):
        as_dates = pd.to_datetime(s, errors="coerce") if not pd.api.types.is_numeric_dtype(s) else None
        if as_dates is not None and as_dates.notna().mean() > 0.8:
            s = as_dates  # dates stored as text / objects
        elif level == "year":
            return s
        else:
            raise ValueError("quarters and months need a date column")
    if level == "year":
        return s.dt.year.astype("Int64")
    if level == "quarter":
        return (s.dt.year.astype("string") + " Q" + s.dt.quarter.astype("string")).astype("category")
    if level == "month":
        return s.dt.to_period("M").astype("string").astype("category")
    raise ValueError(f"unknown level {level}")


def memory_mb(df: pd.DataFrame) -> float:
    return float(df.memory_usage(deep=True).sum() / 2**20)


def numeric_columns(df) -> list[str]:
    return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not np.issubdtype(df[c].dtype, np.bool_)]
