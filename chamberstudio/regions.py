"""Country -> region (for the Region > Country drill-down and region filters)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

from chamberviz.assets_lookup import country_code

_FILE = Path(__file__).with_name("regions.json")
OTHER = "Other"


@lru_cache(maxsize=1)
def _table() -> dict:
    return json.loads(_FILE.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _by_code() -> dict[str, str]:
    out = {}
    for region, info in _table()["regions"].items():
        for code in info["countries"]:
            out[code] = region
    return out


def regions() -> list[str]:
    return list(_table()["regions"])


def region_label(region: str, lang: str = "en") -> str:
    info = _table()["regions"].get(region) or _table()["groups"].get(region) or {}
    return info.get("ar", region) if lang == "ar" else region


@lru_cache(maxsize=4096)
def region_of(country) -> str:
    """'الصين الشعبية' -> 'Asia', 'UAE' -> 'GCC'; unknown names -> 'Other'."""
    code = country_code(str(country)) if country is not None else None
    return _by_code().get(code, OTHER) if code else OTHER


def region_column(s: pd.Series) -> pd.Series:
    """A region for every row of a country column (computed once per distinct country)."""
    uniques = pd.Series(s.dropna().unique())
    mapping = {c: region_of(c) for c in uniques}
    return s.map(mapping).astype("category")


def group_regions(group: str) -> list[str]:
    """'Arab world' -> ['GCC', 'Levant', 'Other Arab countries']; a region -> [itself]."""
    g = _table()["groups"].get(group)
    return list(g["regions"]) if g else [group]
