"""Chamber Studio (Streamlit UI only; the logic lives in data / filters / measures).

    python -m chamberviz dashboard
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

import chamberviz as cv  # noqa: E402
from chamberstudio import data, measures, plotly_theme  # noqa: E402
from chamberstudio import filters as F  # noqa: E402

SAMPLE = ROOT / "examples" / "sample_trade_dashboard.xlsx"
UPLOADS = ROOT / "workspace" / "uploads"
KIND_ICON = {"category": "🏷️", "country": "🌍", "number": "🔢", "date": "📅", "year": "📅", "text": "🔤"}
NUMBER_OPS = {"between": "between", ">": ">", ">=": "≥", "<": "<", "<=": "≤", "=": "=", "!=": "≠",
              "empty": "is empty", "not_empty": "is not empty"}
TEXT_OPS = {"contains": "contains", "not_contains": "does not contain", "starts": "starts with",
            "ends": "ends with", "equals": "equals"}
DATE_PRESETS = {"range": "Between dates", "this_year": "This year", "last_year": "Last year", "ytd": "Year to date",
                "last_12_months": "Last 12 months", "pick": "Pick years / quarters / months"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MAX_OPTIONS = 2000

st.set_page_config(page_title="Chamber Studio", page_icon="📊", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
section[data-testid="stSidebar"] {width: 440px !important; min-width: 440px !important;}
section[data-testid="stSidebar"] .block-container {padding-top: 1.2rem;}
div[data-testid="stSidebarUserContent"] {padding-top: 0.5rem;}
.cs-count {font-size: 0.95rem; padding: 0.35rem 0.6rem; border-radius: 0.5rem; background: rgba(217,169,42,0.12);
           border: 1px solid rgba(217,169,42,0.45); margin-bottom: 0.4rem;}
.cs-muted {opacity: 0.7; font-size: 0.85rem;}
.cs-group {border-left: 3px solid #d9a92a; padding-left: 0.5rem;}
</style>""", unsafe_allow_html=True)

S = st.session_state
S.setdefault("files", {})              # display name -> path on disk
S.setdefault("source", None)           # {"file": name, "sheet": sheet}
S.setdefault("schemas", {})            # "file|sheet" -> schema
S.setdefault("join", None)             # {"file", "sheet", "left_on", "right_on"}
S.setdefault("calcs", [])              # [{"name", "formula"}]
S.setdefault("page_filter", F.Group("and"))
S.setdefault("advanced", False)
S.setdefault("design", "navy_gold")


# ================================================================ data (cached)
@st.cache_resource(show_spinner=False, max_entries=16)
def load_sheets(path: str, mtime: float) -> dict:
    return data.load_file(path)


def sheets_of(name: str) -> dict:
    path = S.files[name]
    return load_sheets(path, Path(path).stat().st_mtime)


def source_key(src) -> str:
    return f"{src['file']}|{src['sheet']}"


@st.cache_resource(show_spinner="Preparing the data…", max_entries=8)
def prepared(path, mtime, sheet, schema_json, join_json, calcs_json):
    """The table the dashboard works on, and the kind of each column."""
    raw = load_sheets(path, mtime)[sheet]
    schema = json.loads(schema_json)
    df = data.apply_schema(raw, schema)
    kinds = {spec.get("label") or col: spec["kind"] for col, spec in schema.items() if not spec.get("hidden")}
    join = json.loads(join_json)
    if join:
        right_raw = load_sheets(join["path"], Path(join["path"]).stat().st_mtime)[join["sheet"]]
        right = data.apply_schema(right_raw, data.default_schema(right_raw))
        df, _ = data.join(df, right, join["left_on"], join["right_on"])
        for col, kind in data.kinds_of(df[[c for c in df.columns if c not in kinds]]).items():
            kinds[col] = kind
        for col in df.columns:
            if col not in kinds:
                kinds[col] = "category"
            if kinds[col] in data.TEXT_KINDS and not isinstance(df[col].dtype, pd.CategoricalDtype):
                df[col] = df[col].astype("string").astype("category")
    for calc in json.loads(calcs_json):
        try:
            df = measures.add_column(df, calc["name"], calc["formula"])
            kinds[calc["name"]] = "number"
        except Exception:
            pass
    return df, kinds


def current():
    """(df, kinds) for the chosen source, or (None, {})."""
    src = S.source
    if not src or src["file"] not in S.files:
        return None, {}
    path = S.files[src["file"]]
    key = source_key(src)
    if key not in S.schemas:
        S.schemas[key] = data.default_schema(sheets_of(src["file"])[src["sheet"]])
    join = dict(S.join) if S.join else None
    if join:
        join["path"] = S.files.get(join["file"])
        if not join["path"]:
            join = None
    return prepared(path, Path(path).stat().st_mtime, src["sheet"], json.dumps(S.schemas[key], ensure_ascii=False),
                    json.dumps(join, ensure_ascii=False), json.dumps(S.calcs, ensure_ascii=False))


@st.cache_resource(show_spinner=False, max_entries=256)
def category_options(df_id: int, _df, column: str) -> list:
    """Values of a column, most frequent first (the list a category filter offers)."""
    counts = _df[column].astype("string").value_counts()
    values = list(counts.index[:MAX_OPTIONS])
    if _df[column].isna().any():
        values.append(F.BLANK)
    return values


# ================================================================ filter cards
def wkey(fid, name):
    return f"f-{fid}-{name}"


def seed(key, value):
    """Give a widget its starting value from the filter spec (only the first time it is drawn)."""
    if key not in S:
        S[key] = value


def remove_filter(fid):
    F.remove(S.page_filter, fid)


def select_all(key, options):
    S[key] = [o for o in options if o != F.BLANK]


def clear_values(key):
    S[key] = []


def card_category(f: F.CategoryFilter, df, kinds):
    opts = category_options(id(df), df, f.column)
    k = wkey(f.id, "values")
    seed(k, [str(v) for v in f.values if str(v) in opts])
    f.values = st.multiselect("Values", opts, key=k, placeholder="Type to search… (none = all)",
                              label_visibility="collapsed")
    c1, c2, c3 = st.columns([1, 1, 1.4], vertical_alignment="center")
    c1.button("All", key=wkey(f.id, "all"), on_click=select_all, args=(k, opts), width="stretch",
              help="Select every value")
    c2.button("None", key=wkey(f.id, "clear"), on_click=clear_values, args=(k,), width="stretch",
              help="Clear the selection (no selection = every row)")
    seed(wkey(f.id, "exclude"), f.exclude)
    f.exclude = c3.toggle("Exclude", key=wkey(f.id, "exclude"),
                          help="Keep every row except the selected values")
    with st.expander("Top / Bottom N", expanded=bool(f.top_n)):
        measures_ = ["(number of rows)"] + [c for c, kd in kinds.items() if kd == "number"]
        seed(wkey(f.id, "top_on"), bool(f.top_n))
        on = st.toggle("Keep only the top / bottom N", key=wkey(f.id, "top_on"),
                       help="Ranked on the rows that the other filters leave (like Power BI)")
        a, b = st.columns(2)
        seed(wkey(f.id, "top_dir"), "Bottom" if f.bottom else "Top")
        direction = a.radio("Which", ["Top", "Bottom"], key=wkey(f.id, "top_dir"), horizontal=True,
                            label_visibility="collapsed")
        seed(wkey(f.id, "top_n"), int(f.top_n or 10))
        n = b.number_input("N", min_value=1, max_value=1000, step=1, key=wkey(f.id, "top_n"),
                           label_visibility="collapsed")
        a, b = st.columns([1.6, 1])
        seed(wkey(f.id, "top_by"), f.top_by if f.top_by in measures_ else measures_[0])
        by = a.selectbox("by", measures_, key=wkey(f.id, "top_by"))
        seed(wkey(f.id, "top_agg"), f.top_agg)
        agg = b.selectbox("measure", list(measures.AGGS), format_func=measures.AGGS.get, key=wkey(f.id, "top_agg"))
        f.top_n = int(n) if on else None
        f.top_by = None if by == measures_[0] else by
        f.top_agg, f.bottom = agg, direction == "Bottom"


def card_number(f: F.NumberFilter, df):
    s = pd.to_numeric(df[f.column], errors="coerce")
    lo, hi = float(s.min()) if s.notna().any() else 0.0, float(s.max()) if s.notna().any() else 0.0
    seed(wkey(f.id, "op"), f.op)
    op = st.selectbox("Condition", list(NUMBER_OPS), format_func=NUMBER_OPS.get, key=wkey(f.id, "op"),
                      label_visibility="collapsed")
    f.op = op
    if op == "between":
        if hi <= lo:
            st.caption(f"Every value is {lo:,.2f}")
            f.value = f.value2 = None
            return
        seed(wkey(f.id, "range"), (f.value if f.value is not None else lo, f.value2 if f.value2 is not None else hi))
        a, b = st.slider("Range", lo, hi, key=wkey(f.id, "range"), label_visibility="collapsed")
        full = abs(a - lo) < 1e-9 and abs(b - hi) < 1e-9
        f.value, f.value2 = (None, None) if full else (a, b)   # the full range filters nothing (keeps empty rows)
    elif op in ("empty", "not_empty"):
        f.value = f.value2 = None
    else:
        seed(wkey(f.id, "value"), f.value if f.value is not None else round((lo + hi) / 2, 2))
        f.value = st.number_input("Value", key=wkey(f.id, "value"), label_visibility="collapsed", format="%.2f")
        f.value2 = None
    st.markdown(f"<span class='cs-muted'>from {lo:,.2f} to {hi:,.2f}</span>", unsafe_allow_html=True)


def card_date(f: F.DateFilter, df, kind):
    s = df[f.column]
    is_date = pd.api.types.is_datetime64_any_dtype(s)
    presets = DATE_PRESETS if is_date else {k: v for k, v in DATE_PRESETS.items() if k not in ("ytd", "last_12_months")}
    seed(wkey(f.id, "preset"), f.preset if f.preset in presets else "range")
    f.preset = st.selectbox("Period", list(presets), format_func=presets.get, key=wkey(f.id, "preset"),
                            label_visibility="collapsed")
    years = sorted({int(y) for y in (s.dt.year if is_date else pd.to_numeric(s, errors="coerce")).dropna().unique()})
    if not years:
        st.caption("No dates in this column")
        return
    if f.preset == "range":
        if is_date:
            lo, hi = s.min().date(), s.max().date()
            start = pd.Timestamp(f.start).date() if f.start else lo
            end = pd.Timestamp(f.end).date() if f.end else hi
            seed(wkey(f.id, "dates"), (start, end))
            got = st.date_input("Between", key=wkey(f.id, "dates"), min_value=lo, max_value=hi,
                                label_visibility="collapsed", format="YYYY-MM-DD")
            if isinstance(got, (tuple, list)) and len(got) == 2:
                a, b = got
                f.start = None if a == lo else a.isoformat()
                f.end = None if b == hi else b.isoformat()
        else:
            if len(years) == 1:
                st.caption(f"Only {years[0]} in the data")
                return
            seed(wkey(f.id, "years_range"), (int(f.start or years[0]), int(f.end or years[-1])))
            a, b = st.select_slider("Years", years, key=wkey(f.id, "years_range"), label_visibility="collapsed")
            f.start = None if a == years[0] else str(a)
            f.end = None if b == years[-1] else str(b)
    elif f.preset == "pick":
        seed(wkey(f.id, "years"), [int(y) for y in f.years if int(y) in years])
        f.years = st.multiselect("Years", years, key=wkey(f.id, "years"), placeholder="Years (none = all)")
        if is_date:
            a, b = st.columns(2)
            seed(wkey(f.id, "quarters"), [int(q) for q in f.quarters])
            f.quarters = a.multiselect("Quarters", [1, 2, 3, 4], format_func=lambda q: f"Q{q}",
                                       key=wkey(f.id, "quarters"), placeholder="Quarters")
            seed(wkey(f.id, "months"), [int(m) for m in f.months])
            f.months = b.multiselect("Months", list(range(1, 13)), format_func=lambda m: MONTHS[m - 1],
                                     key=wkey(f.id, "months"), placeholder="Months")
    else:
        seed(wkey(f.id, "today"), f.anchor == "today")
        today = st.toggle("Count from today (not from the latest date in the data)", key=wkey(f.id, "today"),
                          help="Statistics usually end before today: by default 'this year' is the year of the "
                               "latest date in the data.")
        f.anchor = "today" if today else "data"
        a = F.anchor_date(s, f.anchor)
        st.markdown(f"<span class='cs-muted'>counted from {a:%d %b %Y}</span>", unsafe_allow_html=True)


def card_text(f: F.TextFilter):
    a, b = st.columns([1.1, 1.6])
    seed(wkey(f.id, "op"), f.op)
    f.op = a.selectbox("How", list(TEXT_OPS), format_func=TEXT_OPS.get, key=wkey(f.id, "op"),
                       label_visibility="collapsed")
    seed(wkey(f.id, "text"), f.value)
    f.value = b.text_input("Text", key=wkey(f.id, "text"), placeholder="text…", label_visibility="collapsed")
    seed(wkey(f.id, "case"), f.case_sensitive)
    f.case_sensitive = st.checkbox("Match upper / lower case", key=wkey(f.id, "case"))


def filter_card(f, df, kinds):
    kind = kinds.get(f.column, "category")
    with st.container(border=True):
        head, x = st.columns([5, 1], vertical_alignment="center")
        head.markdown(f"{KIND_ICON.get(kind, '🏷️')} **{f.column}**")
        x.button("", icon=":material/close:", key=wkey(f.id, "remove"), on_click=remove_filter, args=(f.id,),
                 help="Remove this filter", type="tertiary")
        if f.column not in df.columns:
            st.warning("This column is not in the data any more.")
            return
        if isinstance(f, F.CategoryFilter):
            card_category(f, df, kinds)
        elif isinstance(f, F.NumberFilter):
            card_number(f, df)
        elif isinstance(f, F.DateFilter):
            card_date(f, df, kind)
        elif isinstance(f, F.TextFilter):
            card_text(f)


def add_filter(select_key, group_id):
    column = S.get(select_key)
    if not column:
        return
    _, kinds = current()
    group = F.find(S.page_filter, group_id) or S.page_filter
    group.items.append(F.new_filter(column, kinds.get(column, "category")))
    S[select_key] = None


def add_group():
    S.page_filter.items.append(F.Group("or"))
    S.advanced = True


def render_group(g: F.Group, df, kinds, depth=0):
    if depth > 0 or S.advanced:
        a, b, c = st.columns([2.2, 1.2, 0.6])
        seed(wkey(g.id, "logic"), g.logic.upper())
        g.logic = a.radio("Match", ["AND", "OR"], key=wkey(g.id, "logic"), horizontal=True,
                          help="AND: a row must pass every filter below. OR: passing one is enough.",
                          label_visibility="collapsed").lower()
        seed(wkey(g.id, "not"), g.negate)
        g.negate = b.checkbox("NOT", key=wkey(g.id, "not"), help="Keep the rows that do NOT match this group")
        if depth > 0:
            c.button("", icon=":material/close:", key=wkey(g.id, "remove"), on_click=remove_filter, args=(g.id,),
                     help="Remove this group", type="tertiary")
    for item in list(g.items):
        if isinstance(item, F.Group):
            with st.container(border=True):
                st.markdown(f"<div class='cs-group'><b>Group</b> <span class='cs-muted'>"
                            f"({'any' if item.logic == 'or' else 'all'} of these)</span></div>", unsafe_allow_html=True)
                render_group(item, df, kinds, depth + 1)
        else:
            filter_card(item, df, kinds)
    if depth > 0:
        key = wkey(g.id, "add")
        st.selectbox("Add a filter to this group", list(df.columns), index=None, key=key,
                     placeholder="＋ Add a filter to this group…",
                     format_func=lambda c: f"{KIND_ICON.get(kinds.get(c), '')} {c}",
                     on_change=add_filter, args=(key, g.id), label_visibility="collapsed")


def reset_all():
    S.page_filter = F.Group("and")


def fresh_ids(spec):
    for s in F.walk(spec):
        s.id = F._new_id()
    return spec


def sidebar(df, kinds):
    with st.sidebar:
        st.markdown("## 🔎 Filters")
        count_slot = st.empty()
        if df is None:
            st.info("Load data first (Data tab).")
            return count_slot
        render_group(S.page_filter, df, kinds)
        st.selectbox("Add a filter", list(df.columns), index=None, key="add-root", placeholder="＋ Add filter…",
                     format_func=lambda c: f"{KIND_ICON.get(kinds.get(c), '')} {c}",
                     on_change=add_filter, args=("add-root", S.page_filter.id), label_visibility="collapsed")
        a, b = st.columns(2)
        a.toggle("AND / OR groups", key="advanced",
                 help="Combine filters with AND / OR groups, e.g. (Country in China, Egypt AND Value > 500) OR "
                      "Sector = Industry")
        b.button("Reset all", on_click=reset_all, width="stretch", disabled=not S.page_filter.items)
        if S.advanced:
            st.button("＋ Add an OR group", on_click=add_group, width="stretch",
                      help="A group of filters where passing one is enough")
        with st.expander("💾 Presets"):
            name = st.text_input("Preset name", key="preset-name", placeholder="e.g. Arab partners 2025")
            if st.button("Save the current filters", disabled=not name or not S.page_filter.items,
                         width="stretch"):
                F.save_preset(name, S.page_filter)
                st.toast(f"Saved '{name}'")
            names = F.list_presets()
            if names:
                pick = st.selectbox("Saved presets", names, key="preset-pick")
                c1, c2 = st.columns(2)
                if c1.button("Load", width="stretch"):
                    S.page_filter = fresh_ids(F.load_preset(pick))
                    st.rerun()
                if c2.button("Delete", width="stretch"):
                    F.delete_preset(pick)
                    st.rerun()
    return count_slot


# ================================================================ data tab
def store_upload(up) -> str:
    UPLOADS.mkdir(parents=True, exist_ok=True)
    path = UPLOADS / up.name
    path.write_bytes(up.getvalue())
    return str(path)


def use_sample():
    S.files[SAMPLE.name] = str(SAMPLE)
    S.source = {"file": SAMPLE.name, "sheet": "Trade"}


def data_tab(df, kinds, filtered):
    left, right = st.columns([1, 1.25], gap="large")
    with left:
        st.markdown("#### 1. Files")
        ups = st.file_uploader("Excel or CSV files", type=["xlsx", "xls", "csv"], accept_multiple_files=True,
                               key="uploader", label_visibility="collapsed")
        for up in ups or []:
            if up.name not in S.files:
                S.files[up.name] = store_upload(up)
                if S.source is None:
                    S.source = {"file": up.name, "sheet": next(iter(sheets_of(up.name)))}
        st.button("Use the sample trade data", on_click=use_sample, disabled=SAMPLE.name in S.files)
        if not S.files:
            return
        names = list(S.files)
        cur = S.source or {"file": names[0], "sheet": None}
        a, b = st.columns(2)
        file = a.selectbox("File", names, index=names.index(cur["file"]) if cur["file"] in names else 0)
        sheets = list(sheets_of(file))
        sheet = b.selectbox("Sheet", sheets, index=sheets.index(cur["sheet"]) if cur.get("sheet") in sheets else 0)
        if S.source != {"file": file, "sheet": sheet}:
            S.source = {"file": file, "sheet": sheet}
            S.join, S.calcs = None, []
            st.rerun()

        st.markdown("#### 2. Columns")
        key = source_key(S.source)
        raw = sheets_of(file)[sheet]
        schema = S.schemas.setdefault(key, data.default_schema(raw))
        table = pd.DataFrame([{"Column": col, "Type": spec["kind"], "Name": spec.get("label") or col,
                               "Hide": bool(spec.get("hidden")),
                               "Example": ", ".join(map(str, raw[col].dropna().astype(str).unique()[:3]))}
                              for col, spec in schema.items()])
        edited = st.data_editor(
            table, hide_index=True, width="stretch", key=f"schema-{key}", disabled=["Column", "Example"],
            column_config={"Type": st.column_config.SelectboxColumn("Type", options=data.KINDS, required=True,
                                                                     help="How the column is used"),
                           "Name": st.column_config.TextColumn("Name", help="Rename the column"),
                           "Hide": st.column_config.CheckboxColumn("Hide", help="Leave it out of the dashboard"),
                           "Example": st.column_config.TextColumn("Example values", width="medium")})
        new = {r.Column: {"kind": r.Type, "label": (r.Name or r.Column).strip(), "hidden": bool(r.Hide)}
               for r in edited.itertuples()}
        if new != schema:
            S.schemas[key] = new
            st.rerun()

        with st.expander("🔗 Join another sheet (add its columns)", expanded=bool(S.join)):
            join_panel(df)
        with st.expander("🧮 Calculated column", expanded=bool(S.calcs)):
            calc_panel(df)

    with right:
        st.markdown("#### 3. Preview")
        if df is None:
            return
        n_all, n = len(df), len(filtered)
        st.markdown(f"<div class='cs-count'>Showing <b>{n:,}</b> of {n_all:,} rows"
                    f"{' (no filters)' if n == n_all else ''}</div>", unsafe_allow_html=True)
        dates = {c: st.column_config.DatetimeColumn(c, format="YYYY-MM-DD") for c in filtered.columns
                 if pd.api.types.is_datetime64_any_dtype(filtered[c])}
        st.dataframe(filtered.head(1000), width="stretch", height=520, hide_index=True, column_config=dates)
        kinds_line = " · ".join(f"{KIND_ICON.get(k, '')} {c}" for c, k in kinds.items())
        st.caption(f"{len(df.columns)} columns: {kinds_line}. Showing the first 1,000 rows.")


def join_panel(df):
    names = list(S.files)
    j = S.join or {}
    a, b = st.columns(2)
    file = a.selectbox("File", names, index=names.index(j["file"]) if j.get("file") in names else 0, key="join-file")
    sheets = [s for s in sheets_of(file) if not (file == S.source["file"] and s == S.source["sheet"])]
    if not sheets:
        st.caption("No other sheet to join.")
        return
    sheet = b.selectbox("Sheet", sheets, index=sheets.index(j["sheet"]) if j.get("sheet") in sheets else 0,
                        key="join-sheet")
    right = sheets_of(file)[sheet]
    left_cols = [c for c in (df.columns if df is not None else []) if not pd.api.types.is_numeric_dtype(df[c])]
    right_cols = [c for c in right.columns if not pd.api.types.is_numeric_dtype(right[c])]
    if not left_cols or not right_cols:
        st.caption("Both sheets need a text column to match on.")
        return
    common = next((c for c in left_cols if c in right_cols), None)
    a, b = st.columns(2)
    lo = a.selectbox("Match this column", left_cols, index=left_cols.index(j.get("left_on", common) or left_cols[0])
                     if (j.get("left_on", common) in left_cols) else 0, key="join-left")
    ro = b.selectbox("with", right_cols, index=right_cols.index(j.get("right_on", common) or right_cols[0])
                     if (j.get("right_on", common) in right_cols) else 0, key="join-right")
    preview, info = data.join(df[[lo]].drop_duplicates().head(200), right, lo, ro)
    st.caption(f"{info['matched']} of {info['rows']} distinct '{lo}' values found in '{sheet}'")
    st.dataframe(preview.head(5), hide_index=True, width="stretch")
    c1, c2 = st.columns(2)
    if c1.button("Join", type="primary", width="stretch"):
        S.join = {"file": file, "sheet": sheet, "left_on": lo, "right_on": ro}
        st.rerun()
    if S.join and c2.button("Remove the join", width="stretch"):
        S.join = None
        st.rerun()


def calc_panel(df):
    st.caption("Use column names, numbers and + - * / ( ). Names with spaces go in [brackets]. "
               "Functions: abs, round, sqrt, log, min, max, coalesce.")
    a, b = st.columns([1, 2])
    name = a.text_input("New column", key="calc-name", placeholder="Balance")
    formula = b.text_input("Formula", key="calc-formula", placeholder="Exports - Imports  or  [Value (JD thousand)] / 1000")
    if formula:
        try:
            measures.parse(formula, df.columns)
            st.success("The formula is valid.")
        except measures.ExpressionError as exc:
            st.error(str(exc))
    if st.button("Add the column", disabled=not (name and formula)):
        try:
            measures.parse(formula, df.columns)
            S.calcs = [c for c in S.calcs if c["name"] != name] + [{"name": name.strip(), "formula": formula}]
            st.rerun()
        except measures.ExpressionError as exc:
            st.error(str(exc))
    for calc in S.calcs:
        c1, c2 = st.columns([5, 1])
        c1.markdown(f"**{calc['name']}** = `{calc['formula']}`")
        if c2.button("✕", key=f"calc-del-{calc['name']}"):
            S.calcs = [c for c in S.calcs if c["name"] != calc["name"]]
            st.rerun()


# ================================================================ quick look (until the visual builder)
def quick_look(df, filtered, kinds):
    cats = [c for c, k in kinds.items() if k in ("category", "country") and c in df.columns]
    nums = [c for c, k in kinds.items() if k == "number" and c in df.columns]
    if not cats:
        st.info("No category column to chart.")
        return
    a, b, c = st.columns(3)
    cat = a.selectbox("By", cats, key="ql-cat")
    num = b.selectbox("Value", ["(number of rows)", *nums], index=1 if nums else 0, key="ql-num")
    agg = c.selectbox("Measure", list(measures.AGGS), format_func=measures.AGGS.get, key="ql-agg")
    value = None if num.startswith("(") else num
    t = measures.aggregate(filtered, cat, value, agg if value else "count")
    t = measures.sort_table(measures.top_n_other(t, cat, 12, keep_other=False), cat, "desc")
    fig = go.Figure(go.Bar(x=t[cat].astype(str), y=t["value"],
                           marker_color=plotly_theme.highlight_colors(S.design, t["value"].tolist()),
                           hovertemplate="%{x}<br>%{y:,.1f}<extra></extra>"))
    plotly_theme.apply(fig, S.design)
    fig.update_layout(height=460,
                      title=f"{measures.AGGS[agg] if value else 'Rows'} of {value or 'rows'} by {cat} (top 12)")
    st.plotly_chart(fig, width="stretch", key="ql-chart", theme=None)   # theme=None: keep the design's template
    st.caption("A first look at the filtered data in the chosen design. The visual builder comes in stage 3.")


# ================================================================ page
def chips(df):
    active = [i for i in S.page_filter.items if F.is_active(i)]
    if not active:
        return
    with st.container(horizontal=True, gap="small"):
        for item in active:
            st.button(f"{F.describe(item)}  ✕", key=f"chip-{item.id}", on_click=remove_filter, args=(item.id,),
                      help="Remove this filter")
        st.button("Reset all", key="chip-reset", on_click=reset_all, type="tertiary")


def main():
    df, kinds = current()
    count_slot = sidebar(df, kinds)
    head, design = st.columns([4, 1.2])
    head.markdown("# 📊 Chamber Studio")
    design.selectbox("Design", cv.list_designs(), key="design", help="Colours of the charts (same as the exports)")
    filtered = df
    error = None
    if df is not None:
        try:
            filtered = F.apply_filters(df, S.page_filter)
        except Exception as exc:  # a filter that no longer fits the data
            error, filtered = str(exc), df
        n, total = len(filtered), len(df)
        count_slot.markdown(f"<div class='cs-count'>Showing <b>{n:,}</b> of {total:,} rows</div>",
                            unsafe_allow_html=True)
        chips(df)
        if error:
            st.warning(f"A filter could not be applied: {error}")
    data_t, look_t = st.tabs(["📁 Data", "📈 Quick look"])
    with data_t:
        data_tab(df, kinds, filtered)
    with look_t:
        if df is None:
            st.info("Load data first.")
        else:
            quick_look(df, filtered, kinds)


main()
