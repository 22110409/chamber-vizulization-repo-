"""A whole dashboard as one JSON file: data source, pages (filters, KPI row, visuals), design.

    dash = Dashboard(title="Trade 2025", design="navy_gold",
                     data=DataSource("examples/trade.xlsx", "Trade"), pages=[Page("Overview")])
    save(dash, "dashboards/trade.json")        # file paths are stored relative to the JSON file
    dash = load("dashboards/trade.json")
    dash.missing                               # data files that were not found: ask for them

Refreshing a monthly report: load the dashboard, point the data source at the new Excel file
(same sheet and columns) and every page, filter and visual is rebuilt from it.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import filters as F
from .visuals import VisualSpec

FORMAT = 1


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class DataSource:
    path: str | None = None            # absolute in memory; relative to the JSON file on disk
    sheet: str | None = None
    schema: dict = field(default_factory=dict)       # column kinds / names / hidden (data.apply_schema)
    join: dict | None = None           # {"path", "sheet", "left_on", "right_on"}
    calcs: list = field(default_factory=list)        # [{"name", "formula"}]


@dataclass
class Page:
    name: str = "Page 1"
    filters: F.Group = field(default_factory=F.Group)
    kpis: list = field(default_factory=list)          # VisualSpec of type "kpi": the KPI row
    visuals: list = field(default_factory=list)       # VisualSpec: the grid
    grid: int = 2                                     # 1, 2 or 3 columns
    id: str = field(default_factory=_new_id)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "grid": self.grid, "filters": F.to_dict(self.filters),
                "kpis": [k.to_dict() for k in self.kpis], "visuals": [v.to_dict() for v in self.visuals]}

    @classmethod
    def from_dict(cls, d: dict) -> "Page":
        return cls(name=d.get("name", "Page"), filters=F.from_dict(d["filters"]) if d.get("filters") else F.Group(),
                   kpis=[VisualSpec.from_dict(k) for k in d.get("kpis", [])],
                   visuals=[VisualSpec.from_dict(v) for v in d.get("visuals", [])],
                   grid=int(d.get("grid", 2)), id=d.get("id") or _new_id())


@dataclass
class Dashboard:
    title: str = "Dashboard"
    design: str = "navy_gold"
    data: DataSource = field(default_factory=DataSource)
    pages: list = field(default_factory=lambda: [Page()])
    current_page: str | None = None
    missing: list = field(default_factory=list)       # set by load(): [{"role", "path", "name"}]

    def page(self, pid: str | None = None) -> Page:
        return next((p for p in self.pages if p.id == (pid or self.current_page)), self.pages[0])


# ---------------------------------------------------------------- paths
def _relative(path: str | None, base: Path) -> str | None:
    """A path as it is written in the JSON: relative to the JSON's folder (forward slashes), or
    absolute when it is on another drive."""
    if not path:
        return None
    try:
        return Path(os.path.relpath(Path(path).resolve(), base.resolve())).as_posix()
    except ValueError:  # another drive on Windows
        return str(Path(path).resolve())


def _absolute(path: str | None, base: Path) -> tuple[str | None, bool]:
    """A path from the JSON -> (absolute path, found?). A file with the same name next to the JSON
    also counts (dashboards copied together with their data)."""
    if not path:
        return None, True
    p = Path(path)
    full = (p if p.is_absolute() else base / p).resolve()
    if full.exists():
        return str(full), True
    beside = base / p.name
    if beside.exists():
        return str(beside.resolve()), True
    return str(full), False


# ---------------------------------------------------------------- JSON
def to_dict(dash: Dashboard, base_dir) -> dict:
    base = Path(base_dir)
    d = dash.data
    join = dict(d.join) if d.join else None
    if join:
        join["path"] = _relative(join.get("path"), base)
    return {
        "chamberstudio": FORMAT, "title": dash.title, "design": dash.design,
        "data": {"path": _relative(d.path, base), "sheet": d.sheet, "schema": d.schema, "join": join,
                 "calcs": d.calcs},
        "pages": [p.to_dict() for p in dash.pages], "current_page": dash.current_page,
    }


def from_dict(raw: dict, base_dir) -> Dashboard:
    if raw.get("chamberstudio") is None:
        raise ValueError("This is not a Chamber Studio dashboard file.")
    base = Path(base_dir)
    missing = []
    d = raw.get("data") or {}
    path, ok = _absolute(d.get("path"), base)
    if not ok:
        missing.append({"role": "data", "path": path, "name": Path(path).name})
    join = dict(d["join"]) if d.get("join") else None
    if join:
        join["path"], ok = _absolute(join.get("path"), base)
        if not ok:
            missing.append({"role": "join", "path": join["path"], "name": Path(join["path"]).name})
    pages = [Page.from_dict(p) for p in raw.get("pages", [])] or [Page()]
    current = raw.get("current_page") if any(p.id == raw.get("current_page") for p in pages) else pages[0].id
    return Dashboard(title=raw.get("title", "Dashboard"), design=raw.get("design", "navy_gold"),
                     data=DataSource(path, d.get("sheet"), d.get("schema") or {}, join, d.get("calcs") or []),
                     pages=pages, current_page=current, missing=missing)


def save(dash: Dashboard, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_dict(dash, path.parent), ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8")
    return path


def load(path) -> Dashboard:
    path = Path(path)
    return from_dict(json.loads(path.read_text(encoding="utf-8")), path.parent)


def replace_file(dash: Dashboard, role: str, new_path: str) -> Dashboard:
    """Point the data (or the joined sheet) at another file: a missing file found again, or next
    month's Excel with the same layout."""
    if role == "join" and dash.data.join:
        dash.data.join["path"] = str(Path(new_path).resolve())
    else:
        dash.data.path = str(Path(new_path).resolve())
    dash.missing = [m for m in dash.missing if m["role"] != role]
    return dash
