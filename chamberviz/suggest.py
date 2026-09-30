"""The dynamic part: read an Excel/CSV file, understand its columns, and suggest charts."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .assets_lookup import auto_icon, looks_like_countries

TOTAL_WORDS = ("total", "grand total", "sum", "المجموع", "الإجمالي", "الاجمالي", "المجموع الكلي",
               "الإجمالى", "مجموع", "اجمالي", "إجمالي")
SHARE_WORDS = ("share", "percent", "%", "ratio", "نسبة", "حصة", "النسبة", "الحصة")
YEAR_WORDS = ("year", "yr", "سنة", "السنة", "عام", "العام")


# ======================================================================
# Reading messy Excel sheets
# ======================================================================
def _is_year_value(v) -> bool:
    try:
        f = float(str(v).strip().rstrip("*").strip())
    except Exception:
        return False
    return f.is_integer() and 1900 <= f <= 2100


def _year_of(name) -> int | None:
    m = re.fullmatch(r"\s*(\d{4})\s*\*?\s*(\(.*\))?\s*", str(name))
    if m and 1900 <= int(m.group(1)) <= 2100:
        return int(m.group(1))
    return None


def _to_number(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        return s.astype(float)
    t = (s.astype(str).str.replace(",", "", regex=False).str.replace("٬", "", regex=False)
         .str.replace("%", "", regex=False).str.replace(" ", "", regex=False).str.strip()
         .replace({"-": None, "—": None, "": None, "nan": None, "None": None}))
    t = t.str.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789."))
    return pd.to_numeric(t, errors="coerce")


def _is_text(s: pd.Series) -> bool:
    return not (pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s))


def _clean(raw: pd.DataFrame) -> pd.DataFrame:
    raw = raw.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
    if raw.empty:
        return raw
    ncol = raw.shape[1]
    title_lines = []
    header_row = 0
    for r in range(min(15, len(raw))):
        row = raw.iloc[r]
        filled = row.notna().sum()
        if filled >= max(2, int(0.5 * ncol)):
            texts = sum(isinstance(v, str) or _year_of(v) is not None for v in row.dropna())
            if texts >= 0.5 * filled:
                header_row = r
                break
        if filled == 1:
            title_lines.append(str(row.dropna().iloc[0]))
    header = []
    for i, v in enumerate(raw.iloc[header_row]):
        if pd.isna(v) or str(v).strip() == "":
            v = f"Column {i + 1}"
        v = str(int(v)) if isinstance(v, float) and v.is_integer() else str(v).strip()
        while v in header:
            v += "_"
        header.append(v)
    df = raw.iloc[header_row + 1:].copy()
    df.columns = header
    df = df.dropna(how="all").reset_index(drop=True)
    # numbers stored as text
    for c in df.columns:
        if _is_text(df[c]):
            conv = _to_number(df[c])
            nn = df[c].notna().sum()
            if nn and conv.notna().sum() >= 0.8 * nn:
                df[c] = conv
    # remove total rows (keep them in attrs)
    txt_cols = [c for c in df.columns if _is_text(df[c])]
    totals = pd.Series(False, index=df.index)
    for c in txt_cols[:2]:
        low = df[c].astype(str).str.strip().str.lower()
        totals |= low.isin(TOTAL_WORDS) | low.str.startswith(("total", "المجموع", "الإجمالي", "الاجمالي"))
    df.attrs["total_rows"] = df[totals].to_dict("records")
    df = df[~totals].reset_index(drop=True)
    df.attrs["title"] = "  ".join(title_lines) if title_lines else None
    df.attrs["header_row"] = int(header_row)
    return df


def read_excel(path, sheet=None) -> pd.DataFrame | dict:
    """Read an Excel/CSV file and clean it: finds the header row, converts numbers stored
    as text, removes empty rows/columns and 'Total' rows.

    read_excel("data.xlsx")                -> {sheet_name: DataFrame}
    read_excel("data.xlsx", sheet="Imports") -> DataFrame
    """
    path = Path(path)
    if path.suffix.lower() in (".csv", ".txt"):
        raw = pd.read_csv(path, header=None)
        df = _clean(raw)
        return df if sheet is not None else {path.stem: df}
    if sheet is not None:
        return _clean(pd.read_excel(path, sheet_name=sheet, header=None))
    return {name: _clean(raw) for name, raw in pd.read_excel(path, sheet_name=None, header=None).items()}


# ======================================================================
# Column profiling
# ======================================================================
@dataclass
class Column:
    name: str
    kind: str          # number, year, date, country, category
    unique: int
    year: int | None = None


def profile(df: pd.DataFrame) -> list[Column]:
    out = []
    n = len(df)
    for c in df.columns:
        s = df[c]
        nun = int(s.nunique(dropna=True))
        y = _year_of(c)
        if pd.api.types.is_datetime64_any_dtype(s):
            out.append(Column(c, "date", nun))
        elif pd.api.types.is_numeric_dtype(s):
            vals = s.dropna()
            is_year_col = (len(vals) and vals.apply(_is_year_value).all() and
                           (any(w in str(c).lower() for w in YEAR_WORDS) or nun == len(vals)))
            if is_year_col and y is None:
                out.append(Column(c, "year", nun))
            else:
                out.append(Column(c, "number", nun, year=y))
        else:
            vals = s.dropna().astype(str)
            if len(vals) and vals.str.match(r"^\d{4}[-/]\d{1,2}([-/]\d{1,2})?").mean() > 0.8:
                out.append(Column(c, "date", nun))
            elif nun and looks_like_countries(list(vals.unique()), 0.7):
                out.append(Column(c, "country", nun))
            else:
                out.append(Column(c, "category", nun))
    return out


@dataclass
class SheetInfo:
    name: str
    df: pd.DataFrame
    columns: list

    def summary(self) -> str:
        parts = [f"{c.name} ({c.kind})" for c in self.columns]
        return f"Sheet '{self.name}': {len(self.df)} rows | " + ", ".join(parts)


def analyze(file, sheet=None, filters=None) -> list[SheetInfo]:
    """Profile every sheet: which columns are numbers, years, dates, countries, categories.
    filters={"Governorate": ["Amman"]} keeps only those rows (in sheets that have the column)."""
    if isinstance(file, pd.DataFrame):
        sheets = {"data": file}
    else:
        got = read_excel(file, sheet)
        sheets = {sheet: got} if sheet is not None else got
    if filters:
        sheets = {n: apply_filters(df, filters) for n, df in sheets.items()}
    return [SheetInfo(n, df, profile(df)) for n, df in sheets.items() if len(df) and df.shape[1] >= 1]


# ======================================================================
# Filters: "only these rows"
# ======================================================================
def value_label(v) -> str:
    """How a cell value is shown and matched: 2025.0 -> '2025', dates without 00:00:00."""
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        try:
            v = v.item()
        except Exception:
            pass
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, pd.Timestamp) or hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d") if (v.hour, v.minute) == (0, 0) else v.strftime("%Y-%m-%d %H:%M")
    return str(v).strip()


def filter_choices(df: pd.DataFrame, column) -> list[str]:
    """The values a column can be filtered on: in time order for years/dates/numbers, else by how
    often they appear (the biggest groups first)."""
    s = df[column].dropna()
    if pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s):
        values = sorted(s.unique())
    else:
        values = list(s.value_counts().index)
    out = []
    for v in values:
        label = value_label(v)
        if label not in out:
            out.append(label)
    return out


def filter_columns(df: pd.DataFrame, max_values: int = 60) -> list[str]:
    """Columns that make sense as a filter: categories, countries, years, dates (not measures or IDs)."""
    out = []
    for c in profile(df):
        if c.kind in ("category", "country", "year", "date") and 2 <= c.unique <= max_values:
            out.append(c.name)
    return out


def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """Keep the rows whose column value is one of the chosen values (compared as shown, so 2025
    matches 2025.0). Columns the sheet does not have are ignored."""
    out, used = df, {}
    for col, wanted in (filters or {}).items():
        if col not in out.columns or not wanted:
            continue
        wanted = [wanted] if isinstance(wanted, (str, int, float)) else list(wanted)
        want = {value_label(w) for w in wanted}
        mask = out[col].map(lambda v: value_label(v) in want if pd.notna(v) else False)
        used[col] = [label for label in filter_choices(out.loc[mask], col)]
        out = out[mask]
    out = out.reset_index(drop=True)
    out.attrs = {**df.attrs, "filters": {**df.attrs.get("filters", {}), **used}}
    return out


def filters_note(filters: dict, max_values: int = 3) -> str:
    """{'Governorate': ['Amman']} -> 'Governorate: Amman' (for the chart subtitle)."""
    parts = []
    for col, values in (filters or {}).items():
        shown = [value_label(v) for v in values]
        text = ", ".join(shown[:max_values]) + (f" +{len(shown) - max_values}" if len(shown) > max_values else "")
        parts.append(f"{col}: {text}")
    return " · ".join(parts)


# ======================================================================
# Suggestions
# ======================================================================
CHART_NAMES = {
    "barplot": "Bar chart", "barh": "Horizontal bar chart", "multibarplot": "Grouped bar chart",
    "stacked": "Stacked bar chart", "pieplot": "Donut chart", "lineplot": "Line chart",
    "areaplot": "Area chart", "histplot": "Histogram", "boxplot": "Box plot",
    "scatterplot": "Scatter plot", "dotplot": "Dot plot (lollipop)", "dumbbell": "Dumbbell chart",
    "treemap": "Treemap", "heatmap": "Heatmap", "geoplot": "Geo chart (map)",
    "bubblemap": "Bubble map", "flowmap": "Trade-flow map", "kpi_cards": "KPI cards",
}


@dataclass
class Suggestion:
    sheet: str
    chart: str               # key of CHART_NAMES
    score: float
    title: str
    reason: str
    func: str                # chamberviz function name
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    code_body: str = ""
    source_path: str | None = None
    filters: dict = field(default_factory=dict)   # {column: [values as shown]} the rows were limited to

    @property
    def name(self) -> str:
        return CHART_NAMES.get(self.chart, self.chart)

    def render(self, **style):
        import chamberviz as cv
        fn = getattr(cv, self.func)
        kw = dict(self.kwargs)
        kw.setdefault("title", self.title)
        kw.update(style)
        return fn(*self.args, **kw)

    def code(self, design=None, save="chart.png") -> str:
        src = self.source_path or "your_file.xlsx"
        lines = ["import chamberviz as cv", "",
                 f'df = cv.read_excel(r"{src}", sheet={self.sheet!r})']
        if self.filters:
            lines.append(f"df = cv.apply_filters(df, {self.filters!r})")
        body = self.code_body.replace("{TITLE}", repr(self.title))
        extra = (f', design="{design}"' if design else "") + (f', save="{save}"' if save else "")
        body = body.replace("{EXTRA}", extra)
        return "\n".join(lines + [body])

    def __repr__(self):
        return f"<{self.score:.0f}  {self.name}: {self.title}  ({self.sheet})>"


def _q(c):
    return repr(str(c))


def _by(a, b) -> str:
    from .text import has_arabic
    if _year_of(a) is not None:          # "2025 by Country" reads badly -> "Country (2025)"
        return f"{b} ({a})"
    return f"{a} حسب {b}" if has_arabic(str(a) + str(b)) else f"{a} by {b}"


def _ar(*parts) -> bool:
    from .text import has_arabic
    return has_arabic(" ".join(str(p) for p in parts))


def _share_like(name) -> bool:
    n = str(name).lower()
    return any(w in n for w in SHARE_WORDS)


MEASURE_VALUE_WORDS = ("import", "export", "re-export", "reexport", "balance", "مستورد", "صادر",
                       "معاد", "الميزان", "ميزان")


def _measure_dims(df: pd.DataFrame, cats: list) -> list:
    """Category columns whose values name different measures (Imports / Exports / Balance): adding
    their rows together gives a meaningless number, so they are never summed across."""
    out = []
    for c in cats:
        if c.unique > 6:
            continue
        values = [str(v).lower() for v in df[c.name].dropna().unique()]
        if values and sum(any(w in v for w in MEASURE_VALUE_WORDS) for v in values) >= 0.6 * len(values):
            out.append(c)
    return out


def _rank_categories(cats: list, n: int, measure_dims: list) -> list:
    """Best column to compare by first: countries, then columns with a handful of groups; IDs or
    names that differ on every row, and measure-name columns, last."""
    def score(c):
        s = 30 if c.kind == "country" else 0
        s += 20 if 2 <= c.unique <= 12 else (10 if c.unique <= 30 else 0)
        if n > 15 and c.unique >= 0.9 * n:
            s -= 40
        if c in measure_dims:
            s -= 50
        return s
    return sorted(cats, key=score, reverse=True)  # stable: equal scores keep the sheet's order


def _suggest_sheet(info: SheetInfo, path=None, by=None, value=None) -> list[Suggestion]:
    df, cols, sh = info.df, info.columns, info.name
    S: list[Suggestion] = []
    base_title = df.attrs.get("title")
    filters = dict(df.attrs.get("filters") or {})

    sheet_sub = (base_title or "").split("  ")[0].strip() or None
    filter_text = filters_note(filters) or None

    def add(chart, score, title, reason, func, args=(), kwargs=None, code="", note=None):
        """note: what the rows were limited to automatically (e.g. the latest year) - shown in
        the subtitle next to the user's filters, so the chart says what it shows."""
        kwargs = dict(kwargs or {})
        extra = " · ".join(p for p in (filter_text, note) if p)
        if "subtitle" in kwargs:
            if extra:
                kwargs["subtitle"] = f"{kwargs['subtitle']} · {extra}"
        else:
            sub = " · ".join(p for p in (sheet_sub, extra) if p)
            if sub:  # the sheet's own title line (and the filters) become the subtitle
                kwargs["subtitle"] = sub
                code = code.replace("title={TITLE}", f"title={{TITLE}}, subtitle={sub!r}")
        S.append(Suggestion(sh, chart, float(min(score, 99)), title, reason, func,
                            tuple(args), kwargs, code, str(path) if path else None, filters))

    n = len(df)
    nums = [c for c in cols if c.kind == "number"]
    # a column left with a single value (usually because it was filtered) groups nothing
    cats = [c for c in cols if c.kind in ("category", "country") and c.unique > 1]
    times = [c for c in cols if c.kind in ("year", "date") and c.unique > 1]
    measure_dims = _measure_dims(df, cats)
    cats = _rank_categories(cats, n, measure_dims)
    if by is not None:  # the user chose the column to compare by
        cats = sorted(cats, key=lambda c: c.name != by)
        times = sorted(times, key=lambda c: c.name != by)
    if value is not None:  # ... and the value to show
        nums = sorted(nums, key=lambda c: c.name != value)
    wide = sorted([c for c in nums if c.year is not None], key=lambda c: c.year)
    plain_nums = [c for c in nums if c.year is None]
    # "Share %" columns: use them for donuts, not as a second measure next to the real values
    shares = [c for c in plain_nums if _share_like(c.name)]
    if shares and len(shares) < len(plain_nums):
        plain_nums = [c for c in plain_nums if c not in shares]
    else:
        shares = []
    n = len(df)

    # -------- wide tables: one column per year (2021, 2022, 2023 ...)
    if len(wide) >= 2 and cats:
        cat = cats[0]
        ys = [c.name for c in wide]
        last, first = ys[-1], ys[0]
        d = df[[cat.name] + ys].dropna(subset=[last])
        top = d.nlargest(min(len(d), 5), last)
        labels = [str(v) for v in top[cat.name]]
        if len(ys) >= 3:
            add("lineplot", 88, f"{cat.name}: {first}–{last}",
                f"The sheet has one column per year ({first}–{last}), so a line chart shows the trend "
                f"of the top {len(top)} {cat.name} over time.",
                "lineplot", (ys, {l: top.loc[top[cat.name] == l, ys].iloc[0].astype(float).tolist() for l in labels}),
                {"subtitle": f"Top {len(top)} by {last}"},
                f"years = {ys!r}\ntop = df.nlargest(5, {_q(last)})\n"
                f"series = {{r[{_q(cat.name)}]: [r[y] for y in years] for _, r in top.iterrows()}}\n"
                f"cv.lineplot(years, series, title={{TITLE}}{{EXTRA}})")
        dd = d.dropna(subset=[first]).nlargest(min(len(d), 15), last)
        if 2 <= len(dd):
            add("dumbbell", 82, f"{cat.name}: {first} vs {last}",
                f"Two periods per {cat.name} ({first} and {last}); a dumbbell chart shows who grew "
                f"and who fell, with the % change.",
                "dotplot", (dd[cat.name].astype(str).tolist(), dd[last].astype(float).tolist()),
                {"compare": dd[first].astype(float).tolist(), "names": (first, last)},
                f"top = df.dropna(subset=[{_q(first)}]).nlargest(15, {_q(last)})\n"
                f"cv.dotplot(top, x={_q(cat.name)}, y={_q(last)}, compare=top[{_q(first)}].tolist(), "
                f"names=({first!r}, {last!r}), title={{TITLE}}{{EXTRA}})")
        g = d.nlargest(min(len(d), 8), last)
        use = ys[-3:]
        add("multibarplot", 70, f"{cat.name}: {', '.join(use)}",
            f"Grouped bars compare the last {len(use)} years side by side for the top {len(g)} {cat.name}.",
            "multibarplot", (g[cat.name].astype(str).tolist(),
                             {y: g[y].astype(float).fillna(0).tolist() for y in use}), {},
            f"top = df.nlargest(8, {_q(last)})\n"
            f"cv.multibarplot(top[{_q(cat.name)}].tolist(), {{y: top[y].tolist() for y in {use!r}}}, "
            f"title={{TITLE}}{{EXTRA}})")
        if len(d) <= 30 and len(ys) >= 3:
            add("heatmap", 58, f"{cat.name} by year",
                "A heatmap shows every value at once (rows = categories, columns = years).",
                "heatmap", (d.set_index(cat.name)[ys],), {},
                f"cv.heatmap(df.set_index({_q(cat.name)})[{ys!r}], title={{TITLE}}{{EXTRA}})")
        # also treat the last year as the main value column
        plain_nums = [next(c for c in nums if c.name == last)] + plain_nums

    # -------- time column + numbers
    if times and (plain_nums or nums):
        t = times[0]
        vals_cols = [c.name for c in (plain_nums or nums)][:4]
        # a Flow-like column (Imports / Exports): one line per measure, never their sum
        md = next((c for c in measure_dims if c.name != t.name), None)
        base, t_note, t_code = df, None, ""
        if md is not None:
            first_val = filter_choices(df, md.name)[0]
            pv = df.pivot_table(index=t.name, columns=md.name, values=vals_cols[0], aggfunc="sum").sort_index()
            if len(pv) >= 2:
                add("lineplot", 91, f"{vals_cols[0]} by {md.name} over time",
                    f"'{md.name}' names different measures ({', '.join(map(str, pv.columns[:4]))}); each gets "
                    "its own line instead of being added together.",
                    "lineplot", (pv.index.tolist(), {str(c): pv[c].astype(float).fillna(0).tolist() for c in pv.columns}),
                    {}, f"pv = df.pivot_table(index={_q(t.name)}, columns={_q(md.name)}, values={_q(vals_cols[0])}, "
                        f"aggfunc='sum')\ncv.lineplot(pv.index.tolist(), {{str(c): pv[c].tolist() for c in pv.columns}}, "
                        f"title={{TITLE}}{{EXTRA}})")
            base = apply_filters(df, {md.name: [first_val]})
            t_note = f"{md.name}: {first_val}"
            t_code = f"df = cv.apply_filters(df, {{{md.name!r}: [{first_val!r}]}})\n"
        g = base.groupby(t.name, sort=True)[vals_cols].sum(numeric_only=True).reset_index()
        xs = g[t.name].tolist()
        if len(g) >= 3:
            if len(vals_cols) >= 2:
                mx = [g[c].abs().max() for c in vals_cols]
                similar = max(mx) / (min(mx) or 1) < 20
            else:
                similar = False
            if similar:
                add("lineplot", 90, f"{', '.join(vals_cols)} over time",
                    f"'{t.name}' is a time column and {len(vals_cols)} measures share a similar scale, "
                    "so one line chart compares their trends.",
                    "lineplot", (xs, {c: g[c].astype(float).tolist() for c in vals_cols}), {},
                    t_code + f"g = df.groupby({_q(t.name)})[{vals_cols!r}].sum().reset_index()\n"
                    f"cv.lineplot(g, x={_q(t.name)}, y={vals_cols!r}, title={{TITLE}}{{EXTRA}})", note=t_note)
            v0 = vals_cols[0]
            add("lineplot" if not similar else "areaplot", 86 if not similar else 64,
                f"{v0} over time",
                f"'{t.name}' is a time column; a line chart is the clearest way to show how {v0} changes.",
                "lineplot" if not similar else "areaplot", (xs, g[v0].astype(float).tolist()),
                {"show_change": True},
                t_code + f"g = df.groupby({_q(t.name)})[{_q(v0)}].sum().reset_index()\n"
                f"cv.{'lineplot' if not similar else 'areaplot'}(g, x={_q(t.name)}, y={_q(v0)}, "
                f"show_change=True, title={{TITLE}}{{EXTRA}})", note=t_note)
            if len(g) <= 10:
                add("barplot", 68, f"{v0} by {t.name}",
                    f"Only {len(g)} periods, so bars per period also read well.",
                    "barplot", ([str(v) for v in xs], g[v0].astype(float).tolist()),
                    {"highlight": "last", "flags": False},
                    t_code + f"g = df.groupby({_q(t.name)})[{_q(v0)}].sum()\n"
                    f"cv.barplot(g, highlight='last', flags=False, title={{TITLE}}{{EXTRA}})", note=t_note)
        if cats and cats[0] is not md and cats[0].unique <= 8 and len(g) >= 3:
            cat = cats[0]
            v0 = vals_cols[0]
            pv = base.pivot_table(index=t.name, columns=cat.name, values=v0, aggfunc="sum").fillna(0)
            add("lineplot", 80, f"{v0} by {cat.name} over time",
                f"Each {cat.name} becomes its own line ({cat.unique} lines).",
                "lineplot", (pv.index.tolist(), {str(c): pv[c].astype(float).tolist() for c in pv.columns}), {},
                t_code + f"pv = df.pivot_table(index={_q(t.name)}, columns={_q(cat.name)}, values={_q(v0)}, aggfunc='sum')\n"
                f"cv.lineplot(pv.index.tolist(), {{str(c): pv[c].tolist() for c in pv.columns}}, "
                f"title={{TITLE}}{{EXTRA}})", note=t_note)

    # -------- category + number
    # Rows per category must be comparable: when the sheet also has a year/date column (several
    # periods per category), show the latest period instead of adding the years together; and a
    # measure-name column (Imports / Exports) is limited to one measure. Both are said in the subtitle.
    period_limit, measure_limit = {}, {}
    if cats:
        cat_main = cats[0]
        tcol = times[0] if times else None
        if tcol is not None and df.groupby(cat_main.name)[tcol.name].nunique().max() > 1:
            period_limit[tcol.name] = [filter_choices(df, tcol.name)[-1]]
        for m in measure_dims:
            if m is not cat_main:
                measure_limit[m.name] = [filter_choices(df, m.name)[0]]
    cat_limit = {**period_limit, **measure_limit}
    d_cat = apply_filters(df, cat_limit) if cat_limit else df
    cat_note = filters_note(cat_limit) or None
    cat_code = f"df = cv.apply_filters(df, {cat_limit!r})\n" if cat_limit else ""

    def addc(*args, **kw):
        add(*args, note=cat_note, **kw)

    if cats and shares:
        cat = cats[0]
        sh_col = shares[0].name
        g = d_cat.groupby(cat.name, sort=False)[sh_col].sum().dropna().sort_values(ascending=False)
        if 2 <= len(g) <= 12:
            addc("pieplot", 88, _by(sh_col, cat.name),
                f"'{sh_col}' is already a share of the total, so a donut chart fits it directly.",
                "pieplot", ([str(v) for v in g.index], g.astype(float).tolist()),
                {"center_text": None, "show_values": False},
                cat_code + f"g = df.groupby({_q(cat.name)})[{_q(sh_col)}].sum().sort_values(ascending=False)\n"
                f"cv.pieplot(g, center_text=None, show_values=False, title={{TITLE}}{{EXTRA}})")
    if cats and plain_nums:
        cat = cats[0]
        for rank_num, num in enumerate(plain_nums[:2]):
            penalty = 6 * rank_num
            dup = d_cat[cat.name].duplicated().any()
            g = (d_cat.groupby(cat.name, sort=False)[num.name].sum() if dup
                 else d_cat.set_index(cat.name)[num.name]).dropna()
            g = g.sort_values(ascending=False)
            k = len(g)
            if k < 2:
                continue
            labels = [str(v) for v in g.index]
            values = g.astype(float).tolist()
            positive = min(values) >= 0
            is_country = cat.kind == "country"
            prep = cat_code + (f"g = df.groupby({_q(cat.name)})[{_q(num.name)}].sum().sort_values(ascending=False)\n"
                               if dup else
                               f"g = df.set_index({_q(cat.name)})[{_q(num.name)}].sort_values(ascending=False)\n")
            icon_hits = sum(auto_icon(l) is not None for l in labels[:12])
            icons = "auto" if icon_hits >= 0.6 * min(k, 12) else None
            extra = " with flags" if is_country else (" with icons" if icons else "")
            what = _by(num.name, cat.name)
            long_labels = max(len(l) for l in labels) > 18
            if k <= 12:
                addc("barplot", (92 if k <= 8 else 84) - penalty, what,
                    f"{k} {cat.name} values to compare{extra}; a sorted bar chart makes the ranking obvious.",
                    "barplot", (labels, values), {"icons": icons} if icons else {},
                    prep + f"cv.barplot(g{', icons=' + repr(icons) if icons else ''}, title={{TITLE}}{{EXTRA}})")
            if k > 12 or long_labels:
                addc("barh", (86 if k > 12 else 78) - penalty, what,
                  f"{'Many categories' if k > 12 else 'Long labels read better'}: horizontal bars fit "
                  f"{'the top 15 of ' + str(k) if k > 15 else 'all ' + str(k)} items with full names{extra}.",
                  "barplot", (labels[:15], values[:15]), {"horizontal": True, **({"icons": icons} if icons else {})},
                  prep + f"cv.barplot(g.head(15), horizontal=True, title={{TITLE}}{{EXTRA}})")
            if positive and k <= 7:
                addc("pieplot", 74 - penalty, f"حصة {what}" if _ar(what) else f"Share of {what}",
                    f"Only {k} parts of a whole, so a donut shows each share (%) clearly.",
                    "pieplot", (labels, values), {},
                    prep + f"cv.pieplot(g, title={{TITLE}}{{EXTRA}})")
            elif positive and k > 7 and not shares:
                addc("pieplot", 55 - penalty, f"Share of {what}",
                    f"{k} parts: the donut keeps the largest 7 and groups the rest as 'Other'.",
                    "pieplot", (labels, values), {},
                    prep + f"cv.pieplot(g, title={{TITLE}}{{EXTRA}})")
            if positive and 6 <= k <= 40:
                addc("treemap", 62, what,
                    "A treemap shows the size of every part and its share in one picture.",
                    "treemap", (labels[:25], values[:25]), {"icons": icons} if icons else {},
                    prep + f"cv.treemap(g.head(25), title={{TITLE}}{{EXTRA}})")
            if 8 <= k <= 40:
                addc("dotplot", 60, what, "A lollipop chart is a lighter alternative to bars for many items.",
                    "dotplot", (labels[:20], values[:20]), {},
                    prep + f"cv.dotplot(g.head(20), title={{TITLE}}{{EXTRA}})")
            if is_country:
                addc("geoplot", 85 if k >= 5 else 70,
                    f"{num.name} حسب الدولة" if _ar(num.name) else f"{_by(num.name, cat.name)}: map",
                    f"'{cat.name}' contains countries, so the values can be shown on a map.",
                    "geoplot", (labels, values), {},
                    prep + f"cv.geoplot(g, title={{TITLE}}{{EXTRA}})")
                addc("flowmap", 80, f"{num.name}: التدفقات مع الأردن" if _ar(num.name) else f"{_by(num.name, cat.name)}: flows with Jordan",
                    "Countries as trade partners: curved arrows into Jordan, thicker for bigger values.",
                    "flowmap", (labels[:12], values[:12]), {"hub": "Jordan"},
                    prep + f"cv.flowmap(g.head(12), hub='Jordan', title={{TITLE}}{{EXTRA}})")
                addc("bubblemap", 66, f"{num.name} حسب الدولة" if _ar(num.name) else f"{_by(num.name, cat.name)}: bubbles",
                    "Bubbles sized by value on a map, useful when small countries matter.",
                    "geoplot", (labels, values), {"style": "bubbles"},
                    prep + f"cv.geoplot(g, style='bubbles', title={{TITLE}}{{EXTRA}})")
            if dup and len(d_cat) / max(k, 1) >= 4 and k <= 12:
                addc("boxplot", 70, f"Spread of {num.name} by {cat.name}",
                    f"Each {cat.name} appears many times ({n} rows), so a box plot compares their ranges.",
                    "boxplot", (d_cat,), {"x": cat.name, "y": num.name},
                    cat_code + f"cv.boxplot(df, x={_q(cat.name)}, y={_q(num.name)}, title={{TITLE}}{{EXTRA}})")
            # KPI summary
            if num is plain_nums[0]:
                tot = float(np.nansum(values))
                addc("kpi_cards", 50, f"{num.name}: key figures" if not num.year else f"{cat.name} ({num.name}): key figures",
                    "Headline numbers (total, largest item, count) for the top of a report or slide.",
                    "kpi_cards", ([
                        {"label": f"Total {num.name}", "value": tot, "icon": "sum"},
                        {"label": f"Largest {cat.name}", "value": labels[0],
                         **({"flag": labels[0]} if is_country else {"icon": "trophy"}),
                         "note": f"{values[0] / tot * 100:.1f}% of total" if tot else None},
                        {"label": f"Number of {cat.name}", "value": float(k), "decimals": 0, "icon": "list-numbers"},
                    ],), {},
                    prep + "cv.kpi_cards([\n"
                    f"    {{'label': 'Total', 'value': g.sum(), 'icon': 'sum'}},\n"
                    f"    {{'label': 'Largest', 'value': g.index[0]}},\n"
                    f"    {{'label': 'Count', 'value': len(g), 'decimals': 0}},\n"
                    "], title={TITLE}{EXTRA})")

    # -------- two categories + number
    if len(cats) >= 2 and plain_nums:
        a, b = cats[0], cats[1]
        v = plain_nums[0].name
        d_two = apply_filters(df, period_limit) if period_limit else df
        two_note = filters_note(period_limit) or None
        two_code = f"df = cv.apply_filters(df, {period_limit!r})\n" if period_limit else ""
        if a.unique <= 15 and b.unique <= 6:
            pv = d_two.pivot_table(index=a.name, columns=b.name, values=v, aggfunc="sum").fillna(0)
            pv = pv.loc[pv.sum(axis=1).sort_values(ascending=False).index]
            ser = {str(c): pv[c].astype(float).tolist() for c in pv.columns}
            code = two_code + (f"pv = df.pivot_table(index={_q(a.name)}, columns={_q(b.name)}, values={_q(v)}, aggfunc='sum')\n")
            add("multibarplot", 72, f"{v} by {a.name} and {b.name}",
                f"Two groupings ({a.name} × {b.name}): grouped bars compare {b.name} within each {a.name}.",
                "multibarplot", ([str(i) for i in pv.index], ser), {},
                code + f"cv.multibarplot(pv.index.tolist(), {{str(c): pv[c].tolist() for c in pv.columns}}, title={{TITLE}}{{EXTRA}})",
                note=two_note)
            add("stacked", 66, f"{v} by {a.name} and {b.name} (stacked)",
                "Stacked bars show each total and what it is made of.",
                "multibarplot", ([str(i) for i in pv.index], ser), {"stacked": True},
                code + f"cv.multibarplot(pv.index.tolist(), {{str(c): pv[c].tolist() for c in pv.columns}}, stacked=True, title={{TITLE}}{{EXTRA}})",
                note=two_note)
        if a.unique <= 30 and b.unique <= 15:
            add("heatmap", 62, f"{v}: {a.name} × {b.name}",
                "A heatmap shows every combination at once.",
                "heatmap", (d_two,), {"rows": a.name, "columns": b.name, "values": v},
                two_code + f"cv.heatmap(df, rows={_q(a.name)}, columns={_q(b.name)}, values={_q(v)}, title={{TITLE}}{{EXTRA}})",
                note=two_note)

    # -------- two numbers -> scatter
    if len(plain_nums) >= 2 and n >= 5:
        xa, yb = plain_nums[0].name, plain_nums[1].name
        sub = df[[xa, yb] + ([cats[0].name] if cats else [])].dropna()
        if len(sub) >= 5:
            r = float(np.corrcoef(sub[xa].astype(float), sub[yb].astype(float))[0, 1])
            add("scatterplot", 60 + 25 * min(abs(r), 1) - (18 if times else 0), f"{yb} vs {xa}",
                f"Two numeric columns; a scatter plot shows their relationship (r = {r:.2f}).",
                "scatterplot", (sub,), {"x": xa, "y": yb, **({"labels": cats[0].name} if cats else {})},
                f"cv.scatterplot(df, x={_q(xa)}, y={_q(yb)}"
                f"{', labels=' + _q(cats[0].name) if cats else ''}, title={{TITLE}}{{EXTRA}})")

    # -------- one number with many rows -> distribution
    for num in plain_nums[:2]:
        if n >= 20 and num.unique >= 10:
            add("histplot", 66 - (20 if times else 0), f"Distribution of {num.name}",
                f"{n} values of {num.name}: a histogram shows where most values fall.",
                "histplot", (df[num.name].dropna().astype(float).tolist(),), {"xlabel": num.name},
                f"cv.histplot(df[{_q(num.name)}], xlabel={_q(num.name)}, title={{TITLE}}{{EXTRA}})")
            add("boxplot", 52 - (20 if times else 0), f"Spread of {num.name}",
                "A box plot summarises the middle, the range and unusual values.",
                "boxplot", (df,), {"y": num.name},
                f"cv.boxplot(df, y={_q(num.name)}, title={{TITLE}}{{EXTRA}})")

    # unique by (chart, title)
    seen, out = set(), []
    for sgg in sorted(S, key=lambda z: -z.score):
        key = (sgg.chart, sgg.func, str(sgg.kwargs.get("style")), sgg.title)
        if key not in seen:
            seen.add(key)
            out.append(sgg)
    return out


def suggest(file, sheet=None, top=None, verbose=True, filters=None, by=None, value=None) -> list[Suggestion]:
    """Look at an Excel/CSV file (or a DataFrame) and return ranked chart suggestions.

    ideas = cv.suggest("trade.xlsx")
    ideas[0].render(design="ivory_dots").save("best.png")
    print(ideas[0].code())

    filters  only these rows, e.g. {"Governorate": ["Amman"], "Year": [2025]} (in the subtitle)
    by       the column to compare by, e.g. "Governorate" (default: the best one is chosen)
    value    the number column to show, e.g. "Employees" (default: the first measure)
    """
    path = None if isinstance(file, pd.DataFrame) else file
    result = []
    for info in analyze(file, sheet, filters=filters):
        ideas = _suggest_sheet(info, path, by=by, value=value)
        if by is not None or value is not None:
            # charts built on the chosen columns first
            for s in ideas:
                if by is not None:
                    s.score += 10 if _q(by) in s.code_body else -10
                if value is not None:
                    s.score += 6 if _q(value) in s.code_body else -6
                s.score = float(max(0, min(99, s.score)))
            ideas.sort(key=lambda z: -z.score)
        result += ideas[: top or None]
    if verbose:
        _print(result, file)
    return result


def _print(sugs, source):
    cur = None
    for i, s in enumerate(sugs):
        if s.sheet != cur:
            cur = s.sheet
            print(f"\n=== Sheet: {cur} ===")
        bar = "█" * int(s.score / 10)
        print(f"[{i:>2}] {s.score:>4.0f} {bar:<10} {s.name:<24} {s.title}")
        print(f"      why: {s.reason}")
    if not sugs:
        print("No chart suggestions: the sheet needs at least one numeric column.")
