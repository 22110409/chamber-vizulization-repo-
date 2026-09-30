"""Filters as data.

Every filter is a small dataclass that turns into JSON (to_dict / from_dict) and back, so
dashboards and presets can be saved. apply_filters(df, spec) returns the rows that pass.

    spec = Group("or", [
        Group("and", [CategoryFilter("Country", ["China", "Egypt"]), NumberFilter("Value", ">", 500)]),
        CategoryFilter("Sector", ["Industry"]),
    ])
    rows = apply_filters(df, spec)

Rules
  * a category filter with nothing selected lets every row through (like Power BI)
  * Top / Bottom N ranks categories on the rows left by the other filters of the same AND group
  * date presets are relative to the latest date in the data (anchor="data") or to today
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Union

import numpy as np
import pandas as pd

BLANK = "(Blank)"
NUMBER_OPS = ["between", ">", ">=", "<", "<=", "=", "!=", "empty", "not_empty"]
TEXT_OPS = ["contains", "not_contains", "starts", "ends", "equals"]
DATE_PRESETS = ["range", "this_year", "last_year", "ytd", "last_12_months", "pick"]
AGGS = ["sum", "mean", "count", "nunique", "min", "max", "median"]


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------- the specs
@dataclass
class CategoryFilter:
    column: str
    values: list = field(default_factory=list)
    exclude: bool = False             # keep everything except the selected values
    top_n: int | None = None          # keep only the N largest (bottom=True: smallest) categories ...
    top_by: str | None = None         # ... ranked by this measure column (None = number of rows)
    top_agg: str = "sum"
    bottom: bool = False
    id: str = field(default_factory=_new_id, compare=False)   # stable key for the app (not compared)


@dataclass
class NumberFilter:
    column: str
    op: str = "between"
    value: float | None = None
    value2: float | None = None       # upper bound for "between"
    id: str = field(default_factory=_new_id, compare=False)   # stable key for the app (not compared)


@dataclass
class DateFilter:
    column: str
    preset: str = "range"             # range, this_year, last_year, ytd, last_12_months, pick
    start: str | None = None          # "2024-01-01" (range)
    end: str | None = None
    years: list = field(default_factory=list)     # pick: any of these years ...
    quarters: list = field(default_factory=list)  # ... and quarters (1-4) ...
    months: list = field(default_factory=list)    # ... and months (1-12)
    anchor: str = "data"              # presets relative to the latest date in the data, or "today"
    id: str = field(default_factory=_new_id, compare=False)   # stable key for the app (not compared)


@dataclass
class TextFilter:
    column: str
    op: str = "contains"
    value: str = ""
    case_sensitive: bool = False
    id: str = field(default_factory=_new_id, compare=False)   # stable key for the app (not compared)


@dataclass
class Group:
    logic: str = "and"                # "and" / "or"
    items: list = field(default_factory=list)
    negate: bool = False              # NOT (...)
    id: str = field(default_factory=_new_id, compare=False)   # stable key for the app (not compared)


Filter = Union[CategoryFilter, NumberFilter, DateFilter, TextFilter, Group]
_TYPES = {"category": CategoryFilter, "number": NumberFilter, "date": DateFilter, "text": TextFilter, "group": Group}
_NAMES = {v: k for k, v in _TYPES.items()}


# ---------------------------------------------------------------- JSON
def to_dict(spec: Filter) -> dict:
    if isinstance(spec, Group):
        return {"type": "group", "logic": spec.logic, "negate": spec.negate, "id": spec.id,
                "items": [to_dict(i) for i in spec.items]}
    return {"type": _NAMES[type(spec)], **asdict(spec)}


def from_dict(d: dict) -> Filter:
    kind = d.get("type")
    if kind not in _TYPES:
        raise ValueError(f"unknown filter type {kind!r}")
    if kind == "group":
        return Group(d.get("logic", "and"), [from_dict(i) for i in d.get("items", [])], bool(d.get("negate")),
                     id=d.get("id") or _new_id())
    cls = _TYPES[kind]
    known = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in d.items() if k in known})


def dumps(spec: Filter) -> str:
    return json.dumps(to_dict(spec), ensure_ascii=False, indent=2, default=str)


def loads(text: str) -> Filter:
    return from_dict(json.loads(text))


# ---------------------------------------------------------------- masks
def _all(df, value=True) -> np.ndarray:
    return np.full(len(df), value, dtype=bool)


def _labels_isin(s: pd.Series, values) -> np.ndarray:
    """s is one of the values (compared as text, so 2025 matches '2025'; BLANK matches empty)."""
    values = list(values)
    blank = BLANK in values
    wanted = {str(v) for v in values if v != BLANK}
    if isinstance(s.dtype, pd.CategoricalDtype):
        cats = s.cat.categories
        hit = cats[np.array([str(c) in wanted for c in cats], dtype=bool)] if len(cats) else cats
        m = s.isin(hit).to_numpy()
    elif pd.api.types.is_numeric_dtype(s):
        nums = []
        for v in wanted:
            try:
                nums.append(float(v))
            except ValueError:
                pass
        m = s.isin(nums).to_numpy(dtype=bool, na_value=False) if nums else _all(s, False)
    else:
        m = s.astype("string").isin(wanted).to_numpy(dtype=bool, na_value=False)
    if blank:
        m = m | s.isna().to_numpy()
    return m


def top_categories(df: pd.DataFrame, f: CategoryFilter) -> list:
    """The N largest (or smallest) categories of f.column by f.top_by (or row count)."""
    s = df[f.column]
    if f.top_by and f.top_by in df.columns:
        g = df.groupby(f.column, observed=True)[f.top_by].agg(f.top_agg)
    else:
        g = s.value_counts()
    g = g.dropna().sort_values(ascending=f.bottom)
    return list(g.head(int(f.top_n)).index)


def _category_mask(df, f: CategoryFilter, with_top: bool = True) -> np.ndarray:
    s = df[f.column]
    m = _all(df)
    if f.values:
        m = _labels_isin(s, f.values)
        if f.exclude:
            m = ~m
    if with_top and f.top_n:
        sub = df[m] if f.values else df
        m = m & _labels_isin(s, top_categories(sub, f))
    return m


def _number_mask(df, f: NumberFilter) -> np.ndarray:
    s = pd.to_numeric(df[f.column], errors="coerce")
    if f.op == "empty":
        return s.isna().to_numpy()
    if f.op == "not_empty":
        return s.notna().to_numpy()
    v = None if f.value is None else float(f.value)
    arr = s.to_numpy(dtype="float64", na_value=np.nan)
    with np.errstate(invalid="ignore"):
        if f.op == "between":
            m = ~np.isnan(arr)
            if v is not None:
                m &= arr >= v
            if f.value2 is not None:
                m &= arr <= float(f.value2)
            return m
        if v is None:
            return _all(df)
        ops = {">": np.greater, ">=": np.greater_equal, "<": np.less, "<=": np.less_equal,
               "=": np.equal, "!=": np.not_equal}
        if f.op not in ops:
            raise ValueError(f"unknown number operator {f.op!r}")
        return ops[f.op](arr, v) & ~np.isnan(arr)


def anchor_date(s: pd.Series, anchor: str = "data") -> pd.Timestamp:
    if anchor == "today":
        return pd.Timestamp.today().normalize()
    if pd.api.types.is_datetime64_any_dtype(s):
        return s.max()
    y = pd.to_numeric(s, errors="coerce").max()
    return pd.Timestamp(int(y), 12, 31) if pd.notna(y) else pd.Timestamp.today().normalize()


def _year_of(value) -> int:
    text = str(value).strip()
    return pd.Timestamp(text).year if "-" in text else int(float(text))


def _bool(x) -> np.ndarray:
    """A writable bool array (pandas may hand back a read-only view)."""
    return np.array(x.to_numpy(dtype=bool, na_value=False) if hasattr(x, 'to_numpy') else x, dtype=bool)


def _date_mask(df, f: DateFilter) -> np.ndarray:
    s = df[f.column]
    is_date = pd.api.types.is_datetime64_any_dtype(s)
    years = s.dt.year if is_date else pd.to_numeric(s, errors="coerce")
    a = anchor_date(s, f.anchor)
    na = s.isna().to_numpy()
    if f.preset == "this_year":
        m = _bool(years == a.year)
    elif f.preset == "last_year":
        m = _bool(years == a.year - 1)
    elif f.preset == "ytd":
        m = _bool(years == a.year)
        if is_date:
            m &= _bool(s <= a)
    elif f.preset == "last_12_months":
        if is_date:
            m = _bool((s > a - pd.DateOffset(months=12)) & (s <= a))
        else:  # a year column: the latest year
            m = _bool(years == a.year)
    elif f.preset == "range":
        m = ~na.copy()
        if is_date:
            if f.start:
                m &= _bool(s >= pd.Timestamp(f.start))
            if f.end:
                m &= _bool(s <= pd.Timestamp(f.end))
        else:  # a year column: '2024' or '2024-06-30' both mean the year 2024
            if f.start:
                m &= _bool(years >= _year_of(f.start))
            if f.end:
                m &= _bool(years <= _year_of(f.end))
    elif f.preset == "pick":
        m = ~na.copy()
        if f.years:
            m &= _bool(years.isin([int(y) for y in f.years]))
        if f.quarters and is_date:
            m &= _bool(s.dt.quarter.isin([int(q) for q in f.quarters]))
        if f.months and is_date:
            m &= _bool(s.dt.month.isin([int(x) for x in f.months]))
    else:
        raise ValueError(f"unknown date preset {f.preset!r}")
    return m


def _text_mask(df, f: TextFilter) -> np.ndarray:
    if not f.value:
        return _all(df)
    s = df[f.column]
    flags = 0 if f.case_sensitive else re.IGNORECASE
    pattern = re.escape(str(f.value))
    regex = {"contains": pattern, "not_contains": pattern, "starts": "^" + pattern, "ends": pattern + "$",
             "equals": "^" + pattern + "$"}[f.op]

    def test(values: pd.Series) -> np.ndarray:
        return values.astype("string").str.contains(regex, flags=flags, regex=True).to_numpy(dtype=bool, na_value=False)

    if isinstance(s.dtype, pd.CategoricalDtype):  # test each distinct value once
        cats = pd.Series(s.cat.categories)
        hit = cats[test(cats)]
        m = s.isin(hit).to_numpy()
    else:
        m = test(s)
    return ~m & s.notna().to_numpy() if f.op == "not_contains" else m


def _is_top(f) -> bool:
    return isinstance(f, CategoryFilter) and bool(f.top_n)


def mask(df: pd.DataFrame, spec: Filter | None) -> np.ndarray:
    """True for every row that passes the spec."""
    if spec is None:
        return _all(df)
    if isinstance(spec, Group):
        # filters that are not set yet (nothing selected) are left out: in an OR group they would
        # otherwise let every row through
        items = [i for i in spec.items if i is not None and is_active(i)]
        if not items:
            m = _all(df)
        elif spec.logic == "or":
            m = _all(df, False)
            for item in items:
                m |= mask(df, item)
        else:
            m = _all(df)
            for item in items:
                if not _is_top(item):
                    m &= mask(df, item)
            for item in items:  # Top N ranks within what the other filters left
                if _is_top(item):
                    m &= _category_mask(df, item, with_top=False)
                    keep = top_categories(df[m], item)
                    m &= _labels_isin(df[item.column], keep)
        return ~m if spec.negate else m
    if spec.column not in df.columns:
        raise KeyError(f"no column {spec.column!r}")
    if isinstance(spec, CategoryFilter):
        return _category_mask(df, spec)
    if isinstance(spec, NumberFilter):
        return _number_mask(df, spec)
    if isinstance(spec, DateFilter):
        return _date_mask(df, spec)
    if isinstance(spec, TextFilter):
        return _text_mask(df, spec)
    raise TypeError(f"not a filter: {spec!r}")


def apply_filters(df: pd.DataFrame, *specs: Filter | None) -> pd.DataFrame:
    """The rows that pass every spec (e.g. page filters, then a visual's own filters)."""
    m = _all(df)
    for spec in specs:
        if spec is not None:
            m &= mask(df, spec)
    return df[m]


# ---------------------------------------------------------------- editing a tree of filters
def new_filter(column: str, kind: str) -> Filter:
    """An empty filter of the right type for a column kind (it removes nothing until it is set)."""
    if kind == "number":
        return NumberFilter(column, "between")
    if kind in ("date", "year"):
        return DateFilter(column, "range")
    if kind == "text":
        return TextFilter(column)
    return CategoryFilter(column)


def walk(spec: Filter):
    """Every filter and group in a tree (depth first)."""
    yield spec
    if isinstance(spec, Group):
        for item in spec.items:
            yield from walk(item)


def find(spec: Filter, fid: str):
    return next((s for s in walk(spec) if s.id == fid), None)


def parent_of(root: Group, fid: str) -> Group | None:
    for s in walk(root):
        if isinstance(s, Group) and any(i.id == fid for i in s.items):
            return s
    return None


def remove(root: Group, fid: str) -> bool:
    parent = parent_of(root, fid)
    if parent is None:
        return False
    parent.items = [i for i in parent.items if i.id != fid]
    return True


# ---------------------------------------------------------------- helpers for the UI
def columns_used(spec: Filter | None) -> set[str]:
    if spec is None:
        return set()
    if isinstance(spec, Group):
        return set().union(*(columns_used(i) for i in spec.items)) if spec.items else set()
    return {spec.column}


def is_active(spec: Filter | None) -> bool:
    """Does the spec remove anything at all (an empty category filter does not)?"""
    if spec is None:
        return False
    if isinstance(spec, Group):
        return any(is_active(i) for i in spec.items)
    if isinstance(spec, CategoryFilter):
        return bool(spec.values or spec.top_n)
    if isinstance(spec, NumberFilter):
        return spec.op in ("empty", "not_empty") or spec.value is not None or spec.value2 is not None
    if isinstance(spec, TextFilter):
        return bool(spec.value)
    if isinstance(spec, DateFilter):
        return spec.preset != "range" or bool(spec.start or spec.end)
    return True


_WORDS = {
    "en": {"selected": "selected", "not": "not", "top": "top", "bottom": "bottom", "by": "by", "rows": "rows",
           "between": "between", "and": "and", "empty": "is empty", "not_empty": "is not empty",
           "this_year": "this year", "last_year": "last year", "ytd": "year to date",
           "last_12_months": "last 12 months", "contains": "contains", "not_contains": "does not contain",
           "starts": "starts with", "ends": "ends with", "equals": "equals", "AND": "AND", "OR": "OR", "NOT": "NOT"},
    "ar": {"selected": "محدد", "not": "باستثناء", "top": "أعلى", "bottom": "أدنى", "by": "حسب", "rows": "صفوف",
           "between": "بين", "and": "و", "empty": "فارغ", "not_empty": "غير فارغ",
           "this_year": "هذه السنة", "last_year": "السنة الماضية", "ytd": "منذ بداية السنة",
           "last_12_months": "آخر 12 شهراً", "contains": "يحتوي", "not_contains": "لا يحتوي",
           "starts": "يبدأ بـ", "ends": "ينتهي بـ", "equals": "يساوي", "AND": "و", "OR": "أو", "NOT": "ليس"},
}


def _num(v) -> str:
    v = float(v)
    return f"{v:,.0f}" if v.is_integer() else f"{v:,.2f}"


def describe(spec: Filter, lang: str = "en") -> str:
    """A short label for a filter chip: 'Country: 3 selected', 'Value > 500', '(A AND B) OR C'."""
    w = _WORDS["ar" if lang == "ar" else "en"]
    if isinstance(spec, Group):
        parts = [describe(i, lang) for i in spec.items if is_active(i)]
        joined = f" {w[spec.logic.upper()]} ".join(f"({p})" if isinstance(i, Group) and len(i.items) > 1 else p
                                                    for p, i in zip(parts, [i for i in spec.items if is_active(i)]))
        return f"{w['NOT']} ({joined})" if spec.negate else joined
    c = spec.column
    if isinstance(spec, CategoryFilter):
        parts = []
        if spec.values:
            shown = ", ".join(map(str, spec.values)) if len(spec.values) <= 2 else f"{len(spec.values)} {w['selected']}"
            parts.append(f"{w['not']} {shown}" if spec.exclude else shown)
        if spec.top_n:
            parts.append(f"{w['bottom' if spec.bottom else 'top']} {spec.top_n} {w['by']} {spec.top_by or w['rows']}")
        return f"{c}: {' · '.join(parts)}"
    if isinstance(spec, NumberFilter):
        if spec.op in ("empty", "not_empty"):
            return f"{c} {w[spec.op]}"
        if spec.op == "between":
            lo = _num(spec.value) if spec.value is not None else "…"
            hi = _num(spec.value2) if spec.value2 is not None else "…"
            return f"{c} {w['between']} {lo} {w['and']} {hi}"
        return f"{c} {spec.op} {_num(spec.value)}"
    if isinstance(spec, DateFilter):
        if spec.preset == "range":
            return f"{c}: {spec.start or '…'} – {spec.end or '…'}"
        if spec.preset == "pick":
            bits = []
            if spec.years:
                bits.append(", ".join(map(str, spec.years)))
            if spec.quarters:
                bits.append(", ".join(f"Q{q}" for q in spec.quarters))
            if spec.months:
                bits.append(", ".join(pd.Timestamp(2000, int(m), 1).strftime("%b") for m in spec.months))
            return f"{c}: {' · '.join(bits) or '…'}"
        return f"{c}: {w[spec.preset]}"
    if isinstance(spec, TextFilter):
        return f"{c} {w[spec.op]} “{spec.value}”"
    return str(spec)


# ---------------------------------------------------------------- presets
PRESETS = Path(__file__).resolve().parents[1] / "presets"


def _safe_name(name: str) -> str:
    name = re.sub(r"[^\w\- ]+", "", str(name), flags=re.UNICODE).strip()
    if not name:
        raise ValueError("give the preset a name")
    return name


def save_preset(name: str, spec: Filter, folder=PRESETS) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{_safe_name(name)}.json"
    path.write_text(dumps(spec), encoding="utf-8")
    return path


def load_preset(name: str, folder=PRESETS) -> Filter:
    return loads((Path(folder) / f"{_safe_name(name)}.json").read_text(encoding="utf-8"))


def list_presets(folder=PRESETS) -> list[str]:
    folder = Path(folder)
    return sorted(p.stem for p in folder.glob("*.json")) if folder.exists() else []


def delete_preset(name: str, folder=PRESETS) -> None:
    (Path(folder) / f"{_safe_name(name)}.json").unlink(missing_ok=True)
