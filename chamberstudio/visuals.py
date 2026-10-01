"""Visuals: one spec -> a table of numbers -> an interactive Plotly figure or a branded chamberviz chart.

    spec = VisualSpec(type="bar", category="Country", value="Value", agg="sum", top_n=10)
    table, meta = prepare(df, spec, kinds)          # the numbers (after the visual's own filters)
    fig = to_plotly(table, spec, meta, "navy_gold")   # in the app
    chart = to_chamberviz(table, spec, meta, design="navy_gold")   # branded export

Drill-down: a date category has levels year > quarter > month > date, a country category has
region > country. `level` is the level shown, `path` the values drilled into, e.g.
level="month", path=[["year", "2025"], ["quarter", "2025 Q2"]] shows the months of 2025 Q2.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from . import filters as F
from . import measures as M
from . import plotly_theme as PT
from .data import time_parts
from .regions import region_column

TYPES = {"bar": "Bar", "hbar": "Horizontal bar", "grouped": "Grouped bars", "stacked": "Stacked bars",
         "line": "Line", "area": "Area", "donut": "Donut", "treemap": "Treemap", "scatter": "Scatter",
         "map": "Map", "flowmap": "Flow map", "kpi": "KPI card", "table": "Table"}
ICONS = {"bar": "📊", "hbar": "📶", "grouped": "📊", "stacked": "🧱", "line": "📈", "area": "🏔️", "donut": "🍩",
         "treemap": "🟩", "scatter": "✳️", "map": "🗺️", "flowmap": "🛫", "kpi": "🔢", "table": "📋"}
MULTI = {"grouped", "stacked", "line", "area", "table"}      # can split by a legend
NOT_CLICKABLE = {"donut", "treemap"}   # Plotly does not report selections on these: the app offers a picker
TIME_LEVELS = ["year", "quarter", "month", "date"]
GEO_LEVELS = ["region", "country"]
LEVEL_NAMES = {"year": "Year", "quarter": "Quarter", "month": "Month", "date": "Date", "region": "Region",
               "country": "Country"}
SORTS = {"auto": "Automatic", "desc": "Largest first", "asc": "Smallest first", "label": "A → Z", "none": "As in data"}
OTHER = "Other"


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class VisualSpec:
    type: str = "bar"
    category: str | None = None        # axis / slices / countries / points
    value: str | None = None           # None = number of rows
    agg: str = "sum"
    legend: str | None = None          # one series per value
    x_value: str | None = None         # scatter: the horizontal measure
    size: str | None = None            # scatter: bubble size
    title: str = ""
    subtitle: str = ""
    sort: str = "auto"
    top_n: int | None = None
    other: bool = True                 # add the rest up as "Other" (with top_n)
    quick: str = "none"                # a quick calculation (measures.QUICK_CALCS)
    window: int = 3                    # moving average window
    highlight: str | None = "max"      # bar colour highlight: max / min / last / None
    level: str | None = None           # drill level (see the module doc)
    path: list = field(default_factory=list)   # drilled into: [[level, value], ...]
    hub: str = "Jordan"                # flow map centre
    filters: F.Group = field(default_factory=F.Group)   # this visual only
    id: str = field(default_factory=_new_id)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["filters"] = F.to_dict(self.filters)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "VisualSpec":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__ and k != "filters"}
        spec = cls(**known)
        spec.filters = F.from_dict(d["filters"]) if d.get("filters") else F.Group()
        return spec


# ---------------------------------------------------------------- drill levels
def hierarchy(spec: VisualSpec, kinds: dict) -> list[str]:
    kind = kinds.get(spec.category)
    if kind == "date":
        return TIME_LEVELS
    if kind == "year":
        return ["year"]
    if kind == "country":
        return GEO_LEVELS
    return []


def default_level(df: pd.DataFrame, spec: VisualSpec, kinds: dict) -> str | None:
    levels = hierarchy(spec, kinds)
    if not levels:
        return None
    if levels == GEO_LEVELS:
        return "country"
    if levels == ["year"]:
        return "year"
    s = df[spec.category]
    months = s.dt.to_period("M").nunique() if pd.api.types.is_datetime64_any_dtype(s) else 0
    return "month" if months <= 48 else "year"


def level_of(df, spec, kinds) -> str | None:
    levels = hierarchy(spec, kinds)
    return spec.level if spec.level in levels else default_level(df, spec, kinds)


def _level_series(df: pd.DataFrame, column: str, level: str) -> pd.Series:
    if level in ("year", "quarter", "month"):
        return time_parts(df[column], level).astype("string")
    if level == "date":
        return df[column].dt.strftime("%Y-%m-%d")
    if level == "region":
        return region_column(df[column]).astype("string")
    return df[column].astype("string")


def can_drill_down(df, spec, kinds) -> bool:
    levels = hierarchy(spec, kinds)
    lvl = level_of(df, spec, kinds)
    return bool(levels) and lvl in levels and levels.index(lvl) < len(levels) - 1


def drill_down(df, spec: VisualSpec, kinds, value) -> VisualSpec:
    """Show what is inside one bar: 2025 -> its quarters, GCC -> its countries."""
    levels = hierarchy(spec, kinds)
    lvl = level_of(df, spec, kinds)
    if not can_drill_down(df, spec, kinds):
        return spec
    spec.path = [*spec.path, [lvl, str(value)]]
    spec.level = levels[levels.index(lvl) + 1]
    return spec


def drill_up(df, spec: VisualSpec, kinds) -> VisualSpec:
    """Back to the level above (and out of the bar drilled into)."""
    levels = hierarchy(spec, kinds)
    if spec.path:
        spec.level, _ = spec.path[-1]
        spec.path = spec.path[:-1]
        return spec
    lvl = level_of(df, spec, kinds)
    if levels and lvl in levels and levels.index(lvl) > 0:
        spec.level = levels[levels.index(lvl) - 1]
    return spec


def set_level(spec: VisualSpec, level: str | None) -> VisualSpec:
    """Jump to a level directly (the drill path is cleared)."""
    spec.level, spec.path = level, []
    return spec


def _apply_path(df, spec, kinds) -> pd.DataFrame:
    """Keep the rows inside every bar drilled into: path = [[level, value], ...]."""
    for level, value in spec.path:
        if level in TIME_LEVELS + GEO_LEVELS:
            df = df[_level_series(df, spec.category, level).to_numpy() == str(value)]
    return df


def breadcrumb(spec: VisualSpec, kinds, df=None) -> str:
    lvl = level_of(df, spec, kinds) if df is not None else spec.level
    parts = ["All", *(str(v) for _, v in spec.path)]
    return " › ".join(parts) + (f"  ({LEVEL_NAMES.get(lvl, lvl)})" if lvl else "")


# ---------------------------------------------------------------- the numbers
@dataclass
class Meta:
    category: str            # label of the category column in the table
    level: str | None
    time: bool               # the category is a time axis (keep it in time order)
    country: bool            # the category holds countries
    value_label: str
    rows: int                # rows used (after the visual's own filters and the drill path)


def value_label(spec: VisualSpec) -> str:
    base = spec.value or "Rows"
    agg = M.AGGS.get(spec.agg, spec.agg) if spec.value else "Count"
    calc = "" if spec.quick in (None, "none") else f" · {M.QUICK_CALCS[spec.quick]}"
    return f"{agg} of {base}{calc}" if spec.value else f"Number of rows{calc}"


def auto_title(spec: VisualSpec, meta: Meta | None = None) -> str:
    if spec.title:
        return spec.title
    if spec.type == "kpi":
        return value_label(spec)
    what = spec.value or "Rows"
    by = meta.category if meta else spec.category
    if spec.type == "scatter":
        return f"{spec.value or 'Rows'} vs {spec.x_value}" + (f" by {by}" if by else "")
    return f"{what} by {by}" + (f" and {spec.legend}" if spec.legend else "") if by else what


def prepare(df: pd.DataFrame, spec: VisualSpec, kinds: dict) -> tuple[pd.DataFrame, Meta]:
    """The aggregated table a visual shows: columns [category, (legend), value, (x_value, size)]."""
    d = F.apply_filters(df, spec.filters) if F.is_active(spec.filters) else df
    level = level_of(d, spec, kinds)
    d = _apply_path(d, spec, kinds)
    kind = kinds.get(spec.category)
    is_time = kind in ("date", "year")
    cat_name = spec.category
    if spec.type == "kpi":
        table = _kpi_table(d, spec, kinds)
        return table, Meta("", None, False, False, value_label(spec), len(d))
    if spec.category is None:
        raise ValueError("Choose the category field (the axis / slices).")
    if level is not None:
        cat_name = spec.category if level in ("country",) else f"{spec.category} ({LEVEL_NAMES[level].lower()})"
        d = d.assign(**{cat_name: _level_series(d, spec.category, level)})
    legend = spec.legend if spec.legend and spec.legend != spec.category and spec.type in MULTI else None
    by = [cat_name, legend] if legend else [cat_name]
    if spec.type == "scatter":
        if not spec.x_value:
            raise ValueError("A scatter needs an X value (a number column).")
        y = M.aggregate(d, by, spec.value, spec.agg)
        x = M.aggregate(d, by, spec.x_value, spec.agg).rename(columns={"value": "x_value"})
        table = y.merge(x, on=by)
        if spec.size:
            table = table.merge(M.aggregate(d, by, spec.size, spec.agg).rename(columns={"value": "size"}), on=by)
    else:
        table = M.aggregate(d, by, spec.value, spec.agg if spec.value else "count")
    table[cat_name] = table[cat_name].astype("object")
    order = spec.sort if spec.sort != "auto" else ("label" if is_time else "desc")
    if spec.type in ("line", "area") and is_time:
        order = "label"
    if spec.top_n and not is_time:
        table = M.top_n_other(table, cat_name, int(spec.top_n), other=OTHER, keep_other=spec.other)
    table = M.sort_table(table, cat_name, order)
    if spec.quick not in (None, "none"):
        table = M.quick_calc(table, spec.quick, time_col=cat_name if is_time else None,
                             within=legend, window=spec.window)
    meta = Meta(cat_name, level, is_time, (level or kind) == "country" or (kind == "country" and level is None),
                value_label(spec), len(d))
    return table.reset_index(drop=True), meta


def _kpi_table(d: pd.DataFrame, spec: VisualSpec, kinds: dict) -> pd.DataFrame:
    """One row: value, and (when the category is a time column) the previous period and the change."""
    now = M.total(d, spec.value, spec.agg if spec.value else "count")
    out = {"value": [now], "previous": [np.nan], "period": [""], "prev_period": [""]}
    if spec.category and kinds.get(spec.category) in ("date", "year"):
        years = _level_series(d, spec.category, "year").astype(float)
        if years.notna().any():
            last = int(years.max())
            cur = d[years.to_numpy() == last]
            prev = d[years.to_numpy() == last - 1]
            if len(prev) and pd.api.types.is_datetime64_any_dtype(d[spec.category]):
                # compare the same months: a year in progress against the same part of last year
                months = set(cur[spec.category].dt.month)
                prev = prev[prev[spec.category].dt.month.isin(months)]
            out = {"value": [M.total(cur, spec.value, spec.agg if spec.value else "count")],
                   "previous": [M.total(prev, spec.value, spec.agg if spec.value else "count") if len(prev) else np.nan],
                   "period": [str(last)], "prev_period": [str(last - 1)]}
    return pd.DataFrame(out)


# ---------------------------------------------------------------- Plotly (in the app)
def _fmt(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "–"
    a = abs(v)
    for div, sfx in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            return f"{v / div:,.1f}{sfx}"
    return f"{v:,.1f}" if not float(v).is_integer() else f"{v:,.0f}"


def _series(table, meta, spec):
    legend = spec.legend if spec.legend in table.columns else None
    if not legend:
        return {meta.value_label: table}
    return {str(k): g for k, g in table.groupby(legend, sort=False, observed=True)}


def to_plotly(table: pd.DataFrame, spec: VisualSpec, meta: Meta, design: str, height: int = 420,
              show_title: bool = True, selected: list | None = None) -> go.Figure:
    c = PT.colors(design)
    cat = meta.category
    fig = go.Figure()
    t = spec.type
    hover = "%{x}<br>%{y:,.2f}<extra></extra>"
    if t in ("bar", "hbar", "grouped", "stacked"):
        series = _series(table, meta, spec)
        single = len(series) == 1
        for name, g in series.items():
            labels, values = g[cat].astype(str).tolist(), g["value"].tolist()
            kw = dict(name=name, customdata=labels)
            if single and t in ("bar", "hbar"):
                kw["marker_color"] = PT.highlight_colors(design, values, spec.highlight)
            if t == "hbar":
                fig.add_trace(go.Bar(x=values[::-1], y=labels[::-1], orientation="h", customdata=labels[::-1],
                                     hovertemplate="%{y}<br>%{x:,.2f}<extra></extra>",
                                     **{k: (v[::-1] if k == "marker_color" else v) for k, v in kw.items()
                                        if k != "customdata"}))
            else:
                fig.add_trace(go.Bar(x=labels, y=values, hovertemplate=hover, **kw))
        fig.update_layout(barmode="stack" if t == "stacked" else "group", showlegend=not single)
    elif t in ("line", "area"):
        series = _series(table, meta, spec)
        for name, g in series.items():
            fig.add_trace(go.Scatter(x=g[cat].astype(str), y=g["value"], name=name, mode="lines+markers",
                                     fill="tozeroy" if t == "area" and len(series) == 1 else None,
                                     stackgroup="one" if t == "area" and len(series) > 1 else None,
                                     customdata=g[cat].astype(str), hovertemplate=hover))
        fig.update_layout(showlegend=len(series) > 1)
    elif t == "donut":
        total = table["value"].sum()
        fig.add_trace(go.Pie(labels=table[cat].astype(str), values=table["value"], hole=0.58, sort=False,
                             customdata=table[cat].astype(str), textinfo="percent",
                             hovertemplate="%{label}<br>%{value:,.2f} (%{percent})<extra></extra>"))
        fig.add_annotation(text=f"<b>{_fmt(total)}</b><br><span style='font-size:12px'>Total</span>",
                           showarrow=False, font=dict(size=22, color=c["title"]))
    elif t == "treemap":
        fig.add_trace(go.Treemap(labels=table[cat].astype(str), parents=[""] * len(table), values=table["value"],
                                 customdata=table[cat].astype(str), textinfo="label+value+percent root",
                                 marker=dict(colors=PT.highlight_colors(design, table["value"].tolist(), None)),
                                 hovertemplate="%{label}<br>%{value:,.2f}<extra></extra>"))
    elif t == "scatter":
        sizes = None
        if "size" in table.columns and table["size"].max() > 0:
            sizes = (np.sqrt(table["size"].clip(lower=0) / table["size"].max()) * 45 + 8).tolist()
        fig.add_trace(go.Scatter(x=table["x_value"], y=table["value"], mode="markers+text",
                                 text=table[cat].astype(str), textposition="top center", customdata=table[cat].astype(str),
                                 marker=dict(size=sizes or 14, color=c["highlight"], opacity=0.85,
                                             line=dict(width=1, color=c["bar"])),
                                 hovertemplate="%{text}<br>x %{x:,.2f}<br>y %{y:,.2f}<extra></extra>"))
        fig.update_xaxes(title=spec.x_value)
        fig.update_yaxes(title=spec.value)
    elif t in ("map", "flowmap"):
        _geo(fig, table, spec, meta, design)
    elif t == "kpi":
        row = table.iloc[0]
        ref = row["previous"] if not pd.isna(row["previous"]) else None
        fig.add_trace(go.Indicator(mode="number+delta" if ref else "number", value=row["value"],
                                   number=dict(font=dict(size=54, color=c["title"]), valueformat=",.1f"),
                                   delta=dict(reference=ref, relative=True, valueformat=".1%",
                                              increasing=dict(color=c["positive"]), decreasing=dict(color=c["negative"]))
                                   if ref else None,
                                   title=dict(text=f"{auto_title(spec, meta)}"
                                              + (f"<br><span style='font-size:12px'>{row['period']} vs {row['prev_period']}</span>"
                                                 if ref else ""), font=dict(size=15))))
        height = min(height, 220)
    PT.apply(fig, design)
    if selected:
        _dim_unselected(fig, [str(v) for v in selected])
    titled = show_title and t != "kpi"
    fig.update_layout(title=dict(text=auto_title(spec, meta) if titled else None), height=height,
                      margin=dict(l=40, r=20, t=60 if titled else (36 if t != "kpi" else 20), b=40),
                      clickmode="event+select")
    if t in ("bar", "grouped", "stacked", "line", "area"):
        # categories stay categories: Plotly would read '2023' as a number and '2025-01-01' as a time axis
        labels = table[cat].astype(str).unique() if cat in table.columns else []
        long = len(labels) > 8 or (len(labels) > 4 and max((len(x) for x in labels), default=0) > 7)
        fig.update_xaxes(type="category", automargin=True, tickangle=-35 if long else 0,
                         nticks=12 if len(labels) > 14 else None)
    if t == "hbar":
        fig.update_layout(margin=dict(l=10))
        fig.update_yaxes(type="category", automargin=True)
    return fig


def _dim_unselected(fig: go.Figure, selected: list[str]) -> None:
    """Power BI style: the selected bars / slices stay bright, the others fade."""
    for tr in fig.data:
        cd = list(tr.customdata) if getattr(tr, "customdata", None) is not None else None
        if not cd:
            continue
        on = [str(c[0] if isinstance(c, (list, tuple)) else c) in selected for c in cd]
        if tr.type == "pie":
            tr.pull = [0.08 if o else 0 for o in on]
            tr.marker.line.width = 2
        elif tr.type in ("bar", "scatter", "scattergeo"):
            tr.marker.opacity = [1.0 if o else 0.28 for o in on]
        elif tr.type == "choropleth":
            tr.marker.opacity = 1.0
            tr.z = [z if o else None for z, o in zip(tr.z, on)]


def _geo(fig, table, spec, meta, design):
    from chamberviz.assets_lookup import country_info
    c = PT.colors(design)
    rows = []
    for label, value in zip(table[meta.category].astype(str), table["value"]):
        info = country_info(label)
        if info and not pd.isna(value):
            rows.append((label, value, info["iso3"], info["lon"], info["lat"]))
    if not rows:
        fig.add_annotation(text="No country names recognised in this field", showarrow=False)
        return
    labels, values, iso3, lon, lat = map(list, zip(*rows))
    if spec.type == "map":
        seq = PT.template(design).layout.colorscale.sequential
        fig.add_trace(go.Choropleth(locations=iso3, z=values, text=labels, customdata=labels, colorscale=seq,
                                    marker_line_color=c["background"], colorbar=dict(thickness=10, len=0.6),
                                    hovertemplate="%{text}<br>%{z:,.2f}<extra></extra>"))
    else:
        hub = country_info(spec.hub or "Jordan") or {"lon": 36.2, "lat": 30.6, "iso3": "JOR"}
        top = max(values) or 1
        for label, value, x, y in zip(labels, values, lon, lat):
            fig.add_trace(go.Scattergeo(lon=[x, hub["lon"]], lat=[y, hub["lat"]], mode="lines",
                                        line=dict(width=1 + 7 * value / top, color=c["highlight"]), opacity=0.75,
                                        hoverinfo="skip", showlegend=False))
        fig.add_trace(go.Scattergeo(lon=lon, lat=lat, text=labels, customdata=labels, mode="markers",
                                    marker=dict(size=[6 + 18 * v / top for v in values], color=c["highlight"],
                                                line=dict(width=1, color=c["background"])),
                                    hovertemplate="%{text}<br>%{customdata}<extra></extra>", showlegend=False))
        fig.add_trace(go.Scattergeo(lon=[hub["lon"]], lat=[hub["lat"]], text=[spec.hub], mode="markers+text",
                                    textposition="bottom center", marker=dict(size=12, color=c["accent"],
                                                                              symbol="star"), showlegend=False))
    fig.update_geos(projection_type="natural earth", showcountries=True, showcoastlines=False, showframe=False,
                    fitbounds="locations")


# ---------------------------------------------------------------- chamberviz (branded export)
def to_chamberviz(table: pd.DataFrame, spec: VisualSpec, meta: Meta, **style):
    """The same numbers as a branded chamberviz chart (logo, design, flags, icons)."""
    import chamberviz as cv
    cat = meta.category
    title = auto_title(spec, meta)
    kw = dict(title=title, **style)
    if spec.subtitle and "subtitle" not in style:
        kw["subtitle"] = spec.subtitle
    t = spec.type
    if t in ("bar", "hbar"):
        return cv.barplot(table[cat].astype(str).tolist(), table["value"].astype(float).tolist(),
                          horizontal=t == "hbar", highlight=spec.highlight, flags="auto" if meta.country else False,
                          **kw)
    if t in ("grouped", "stacked", "line", "area"):
        series = {name: g.set_index(cat)["value"] for name, g in _series(table, meta, spec).items()}
        labels = list(dict.fromkeys(table[cat].astype(str)))
        data = {n: [float(s.get(l, s.get(str(l), 0)) if l in s.index else 0) for l in labels]
                for n, s in ((n, s.rename(index=str)) for n, s in series.items())}
        if t in ("grouped", "stacked"):
            return cv.multibarplot(labels, data, stacked=t == "stacked", **kw)
        return cv.lineplot(labels, data if len(data) > 1 else next(iter(data.values())), area=t == "area", **kw)
    if t == "donut":
        return cv.pieplot(table[cat].astype(str).tolist(), table["value"].astype(float).tolist(), **kw)
    if t == "treemap":
        return cv.treemap(table[cat].astype(str).tolist(), table["value"].astype(float).tolist(), **kw)
    if t == "scatter":
        d = table.rename(columns={"value": spec.value or "Rows", "x_value": spec.x_value})
        return cv.scatterplot(d, x=spec.x_value, y=spec.value or "Rows", labels=cat, **kw)
    if t == "map":
        return cv.geoplot(table[cat].astype(str).tolist(), table["value"].astype(float).tolist(), **kw)
    if t == "flowmap":
        return cv.flowmap(table[cat].astype(str).tolist(), table["value"].astype(float).tolist(), hub=spec.hub, **kw)
    if t == "kpi":
        row = table.iloc[0]
        change = None if pd.isna(row["previous"]) or not row["previous"] else round((row["value"] / row["previous"] - 1) * 100, 1)
        return cv.kpi_cards([{"label": title, "value": float(row["value"]), "change": change,
                              "note": f"{row['period']} vs {row['prev_period']}" if change is not None else None}],
                            title=kw.pop("title"), **{k: v for k, v in kw.items() if k != "title"})
    raise ValueError(f"'{TYPES.get(t, t)}' cannot be exported as a branded image (export the data instead)")


# ---------------------------------------------------------------- suggestions
_SUGGEST_TYPE = {"barplot": "bar", "barh": "hbar", "pieplot": "donut", "treemap": "treemap", "dotplot": "hbar",
                 "geoplot": "map", "bubblemap": "map", "flowmap": "flowmap", "lineplot": "line", "areaplot": "area",
                 "multibarplot": "grouped", "stacked": "stacked", "scatterplot": "scatter", "kpi_cards": "kpi",
                 "heatmap": "table"}


def from_suggestion(sug, df: pd.DataFrame) -> VisualSpec | None:
    """Turn a cv.suggest() idea into a visual spec (None when it has no counterpart)."""
    kind = _SUGGEST_TYPE.get(sug.chart)
    if kind is None:
        return None
    cols = [c for c in re.findall(r"'([^']*)'", sug.code_body) if c in df.columns]
    cols = list(dict.fromkeys(cols))
    if not cols:
        return None
    spec = VisualSpec(type=kind, title=sug.title)
    nums = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
    texts = [c for c in cols if c not in nums]
    if kind == "scatter":
        if len(nums) < 2:
            return None
        spec.x_value, spec.value = nums[0], nums[1]
        spec.category = texts[0] if texts else None
        if spec.category is None:
            return None
    elif kind == "kpi":
        spec.value = nums[0] if nums else None
    else:
        spec.category = texts[0] if texts else cols[0]
        spec.value = nums[0] if nums else None
        if kind in ("grouped", "stacked", "line", "area") and len(texts) > 1:
            spec.legend = texts[1]
        if kind in ("hbar", "bar") and len(set(df[spec.category].dropna())) > 12:
            spec.top_n, spec.type = 15, "hbar"
    if "top" in sug.code_body and spec.top_n is None and kind not in ("line", "area", "kpi", "scatter"):
        m = re.search(r"head\((\d+)\)", sug.code_body)
        spec.top_n = int(m.group(1)) if m else None
    return spec


def suggest(df: pd.DataFrame, top: int = 8) -> list[VisualSpec]:
    """The best chart ideas for the (filtered) data, as visual specs."""
    import chamberviz as cv
    if df is None or df.empty:
        return []
    plain = df.copy()
    for c in plain.columns:
        if isinstance(plain[c].dtype, pd.CategoricalDtype):
            plain[c] = plain[c].astype("object")
    out, seen = [], set()
    for sug in cv.suggest(plain, verbose=False):
        spec = from_suggestion(sug, df)
        if spec is None:
            continue
        key = (spec.type, spec.category, spec.value, spec.legend, spec.x_value)
        if key in seen:
            continue
        seen.add(key)
        out.append(spec)
        if len(out) >= top:
            break
    return out


# ---------------------------------------------------------------- cross-filtering
def series_names(table: pd.DataFrame, meta: Meta, spec: VisualSpec) -> list[str]:
    """Trace names in the order to_plotly draws them (curve_number -> legend value)."""
    return list(_series(table, meta, spec))


def selection_from_points(spec: VisualSpec, table: pd.DataFrame, meta: Meta, points: list[dict]) -> dict | None:
    """Clicked / selected points of a chart -> a selection that can filter the other visuals.
    Points are Plotly selection points (customdata holds the category label)."""
    if not points or spec.type in ("kpi", "table") or not spec.category:
        return None
    labels = set(table[meta.category].astype(str)) if meta.category in table.columns else set()
    values, legend_values = [], []
    names = series_names(table, meta, spec) if spec.legend in table.columns else []
    for p in points:
        cd = p.get("customdata")
        if isinstance(cd, (list, tuple)):
            cd = cd[0] if cd else None
        label = next((str(v) for v in (cd, p.get("label"), p.get("x") if spec.type != "hbar" else p.get("y"))
                      if v is not None and str(v) in labels), None)
        if label is None or label == OTHER:
            continue
        if label not in values:
            values.append(label)
        curve = p.get("curve_number")
        if names and curve is not None and 0 <= curve < len(names) and names[curve] not in legend_values:
            legend_values.append(names[curve])
    if not values:
        return None
    return {"visual": spec.id, "title": auto_title(spec, meta), "column": spec.category, "level": meta.level,
            "values": values, "legend": spec.legend if legend_values else None, "legend_values": legend_values}


def selection_mask(df: pd.DataFrame, sel: dict | None) -> np.ndarray:
    """Rows that belong to the selected bars / slices (at the level they were clicked at)."""
    if not sel or sel.get("column") not in df.columns:
        return np.ones(len(df), dtype=bool)
    level = sel.get("level")
    s = _level_series(df, sel["column"], level) if level else df[sel["column"]].astype("string")
    m = np.array(s.isin([str(v) for v in sel["values"]]).to_numpy(dtype=bool, na_value=False))  # writable
    if sel.get("legend") and sel.get("legend_values") and sel["legend"] in df.columns:
        m &= df[sel["legend"]].astype("string").isin(sel["legend_values"]).to_numpy(dtype=bool, na_value=False)
    return m


def describe_selection(sel: dict) -> str:
    vals = sel["values"]
    shown = ", ".join(vals[:3]) + (f" +{len(vals) - 3}" if len(vals) > 3 else "")
    name = LEVEL_NAMES.get(sel.get("level"), sel.get("level"))
    level = f" ({name})" if sel.get("level") and str(name).lower() != str(sel["column"]).lower() else ""
    extra = f" · {sel['legend']}: {', '.join(sel['legend_values'])}" if sel.get("legend") else ""
    return f"{sel['column']}{level}: {shown}{extra}"
