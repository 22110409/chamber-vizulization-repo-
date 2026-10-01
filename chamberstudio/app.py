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
from chamberstudio import visuals as V  # noqa: E402
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


def filter_roots() -> list:
    """The page's filters and every visual's own filters."""
    return [S.page_filter] + [v.filters for v in S.get("visuals", [])]


def remove_filter(fid):
    for root in filter_roots():
        if F.remove(root, fid):
            return


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
    c1, c2 = st.columns(2)
    c1.button("All", key=wkey(f.id, "all"), on_click=select_all, args=(k, opts), width="stretch",
              help="Select every value")
    c2.button("None", key=wkey(f.id, "clear"), on_click=clear_values, args=(k,), width="stretch",
              help="Clear the selection (no selection = every row)")
    seed(wkey(f.id, "exclude"), f.exclude)
    f.exclude = st.toggle("Exclude the selected values", key=wkey(f.id, "exclude"),
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
    group = next((g for g in (F.find(r, group_id) for r in filter_roots()) if g is not None), S.page_filter)
    group.items.append(F.new_filter(column, kinds.get(column, "category")))
    S[select_key] = None


def add_group():
    S.page_filter.items.append(F.Group("or"))
    S.advanced = True


def render_group(g: F.Group, df, kinds, depth=0, advanced=None, add_here=False):
    advanced = S.advanced if advanced is None else advanced
    if depth > 0 or advanced:
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
                render_group(item, df, kinds, depth + 1, advanced)
        else:
            filter_card(item, df, kinds)
    if depth > 0 or add_here:
        key = wkey(g.id, "add")
        st.selectbox("Add a filter to this group", list(df.columns), index=None, key=key,
                     placeholder="＋ Add a filter to this group…" if depth > 0 else "＋ Add a filter to this visual…",
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


# ================================================================ report: visuals
AGG_NAMES = measures.AGGS
QUICK_NAMES = measures.QUICK_CALCS
HIGHLIGHTS = {"max": "Largest", "min": "Smallest", "last": "Last", None: "None"}
ROWS = "(number of rows)"


def vkey(spec, name):
    return f"v-{spec.id}-{name}"


def columns_of(kinds, df, wanted):
    return [c for c, k in kinds.items() if k in wanted and c in df.columns]


def new_visual(df, kinds, kind="bar") -> V.VisualSpec:
    cats = columns_of(kinds, df, ("country", "category")) or columns_of(kinds, df, ("date", "year"))
    nums = columns_of(kinds, df, ("number",))
    return V.VisualSpec(kind, cats[0] if cats else None, nums[0] if nums else None)


def add_visual():
    df, kinds = current()
    spec = new_visual(df, kinds)
    S.visuals.append(spec)
    S.selected = spec.id


def add_suggested(spec_dict):
    spec = V.VisualSpec.from_dict(spec_dict)
    spec.id = V._new_id()
    S.visuals.append(spec)
    S.selected = spec.id


def select_visual(vid):
    S.selected = None if S.get("selected") == vid else vid


def delete_visual(vid):
    S.visuals = [v for v in S.visuals if v.id != vid]
    if S.get("selected") == vid:
        S.selected = None


def duplicate_visual(vid):
    i = next(i for i, v in enumerate(S.visuals) if v.id == vid)
    copy = V.VisualSpec.from_dict(S.visuals[i].to_dict())
    copy.id = V._new_id()
    for s in F.walk(copy.filters):
        s.id = F._new_id()
    S.visuals.insert(i + 1, copy)


def move_visual(vid, step):
    i = next(i for i, v in enumerate(S.visuals) if v.id == vid)
    j = i + step
    if 0 <= j < len(S.visuals):
        S.visuals[i], S.visuals[j] = S.visuals[j], S.visuals[i]


def drill_into(vid, key):
    df, kinds = current()
    spec = next(v for v in S.visuals if v.id == vid)
    value = S.get(key)
    if value:
        V.drill_down(F.apply_filters(df, S.page_filter), spec, kinds, value)
    S[key] = None


def drill_up(vid):
    df, kinds = current()
    spec = next(v for v in S.visuals if v.id == vid)
    V.drill_up(df, spec, kinds)


def chart_key(spec):
    """A new key generation clears every chart's click selection (Streamlit cannot reset it otherwise)."""
    return f"v-{spec.id}-chart-{S.get('sel_gen', 0)}"


def reset_chart_selections():
    S.sel_gen = S.get("sel_gen", 0) + 1
    S.sel_seen = {}


def clear_selection():
    S.selection = None
    reset_chart_selections()


def _points(state) -> list:
    try:
        return list(state["selection"]["points"])
    except (KeyError, TypeError):
        return []


def process_clicks(filtered, kinds):
    """Turn the newest click in any chart into the page's selection (or a drill-down)."""
    for spec in S.visuals:
        state = S.get(chart_key(spec))
        if state is None:          # this chart has not been clicked since it was drawn
            continue
        pts = _points(state)
        sig = json.dumps(sorted(json.dumps(p, sort_keys=True, default=str) for p in pts))
        seen = S.sel_seen.get(spec.id)
        if seen == sig:
            continue
        S.sel_seen[spec.id] = sig
        if not pts and seen is None:
            continue   # a chart that was just drawn starts with an empty selection: not a click
        try:
            table, meta = V.prepare(filtered, spec, kinds)
        except Exception:
            continue
        sel = V.selection_from_points(spec, table, meta, pts)
        if sel is None:
            if S.selection and S.selection["visual"] == spec.id:   # clicked away: selection cleared
                S.selection = None
            continue
        if S.get("click_drill") and len(sel["values"]) == 1 and V.can_drill_down(filtered, spec, kinds):
            V.drill_down(filtered, spec, kinds, sel["values"][0])
            if S.selection and S.selection["visual"] == spec.id:
                S.selection = None
        else:
            S.selection = sel
        reset_chart_selections()
        st.rerun()


def select_from_picker(vid, key):
    """The '🎯 Select…' picker of donuts / treemaps: the same selection a click on a bar gives."""
    df, kinds = current()
    filtered = F.apply_filters(df, S.page_filter)
    spec = next(v for v in S.visuals if v.id == vid)
    values = S.get(key) or []
    if not values:
        if S.selection and S.selection["visual"] == vid:
            S.selection = None
        return
    table, meta = V.prepare(filtered, spec, kinds)
    S.selection = V.selection_from_points(spec, table, meta, [{"customdata": v} for v in values])


def data_for(spec, filtered):
    """Every visual except the one clicked is filtered by the selection."""
    sel = S.get("selection")
    if not sel or sel["visual"] == spec.id:
        return filtered
    return filtered[V.selection_mask(filtered, sel)]


def visual_card(spec: V.VisualSpec, filtered, kinds):
    selected = S.get("selected") == spec.id
    with st.container(border=True):
        head = st.columns([6, 1, 1, 1, 1], vertical_alignment="center")
        head[0].markdown(f"{V.ICONS.get(spec.type, '')} **{V.auto_title(spec) if not spec.title else spec.title}**"
                         + ("  <span class='cs-muted'>· editing</span>" if selected else ""), unsafe_allow_html=True)
        head[1].button("", icon=":material/edit:", key=vkey(spec, "edit"), on_click=select_visual, args=(spec.id,),
                       type="primary" if selected else "tertiary", help="Settings of this visual")
        head[2].button("", icon=":material/content_copy:", key=vkey(spec, "dup"), on_click=duplicate_visual,
                       args=(spec.id,), type="tertiary", help="Duplicate")
        head[3].button("", icon=":material/arrow_upward:", key=vkey(spec, "up"), on_click=move_visual,
                       args=(spec.id, -1), type="tertiary", help="Move earlier")
        head[4].button("", icon=":material/delete:", key=vkey(spec, "del"), on_click=delete_visual,
                       args=(spec.id,), type="tertiary", help="Delete")
        try:
            table, meta = V.prepare(filtered, spec, kinds)
        except Exception as exc:
            st.info(f"{exc}")
            return
        if V.hierarchy(spec, kinds) and spec.type not in ("kpi",):   # a KPI uses its date column only to compare
            d1, d2, d3 = st.columns([0.5, 2.6, 2.2], vertical_alignment="center")
            d1.button("", icon=":material/undo:", key=vkey(spec, "drillup"), on_click=drill_up, args=(spec.id,),
                      type="tertiary",
                      disabled=not spec.path and V.hierarchy(spec, kinds).index(meta.level or V.hierarchy(spec, kinds)[0]) == 0,
                      help="Drill up: back to the level above")
            d2.markdown(f"<span class='cs-muted'>{V.breadcrumb(spec, kinds, filtered)}</span>", unsafe_allow_html=True)
            if V.can_drill_down(filtered, spec, kinds):
                key = vkey(spec, "drill")
                d3.selectbox("Drill into", table[meta.category].astype(str).tolist(), index=None, key=key,
                             placeholder="⤵ Drill into…", on_change=drill_into, args=(spec.id, key),
                             label_visibility="collapsed")
        if F.is_active(spec.filters):
            st.markdown(f"<span class='cs-muted'>🔎 this visual only: {F.describe(spec.filters)}</span>",
                        unsafe_allow_html=True)
        if spec.type in V.NOT_CLICKABLE:
            key = f"{vkey(spec, 'pick')}-{S.get('sel_gen', 0)}"
            sel = S.get("selection")
            mine = sel["values"] if sel and sel["visual"] == spec.id else []
            options = [x for x in table[meta.category].astype(str) if x != V.OTHER]
            seed(key, [m for m in mine if m in options])
            st.multiselect("🎯 Select", options, key=key, placeholder="🎯 Select slices to filter the other visuals…",
                           on_change=select_from_picker, args=(spec.id, key), label_visibility="collapsed")
        if spec.type == "table":
            show = table.rename(columns={"value": meta.value_label})
            st.dataframe(show, hide_index=True, width="stretch", height=360)
            return
        sel = S.get("selection")
        mine = sel["values"] if sel and sel["visual"] == spec.id else None
        fig = V.to_plotly(table, spec, meta, S.design, height=380 if S.grid > 1 else 460, show_title=False,
                          selected=mine)
        selectable = spec.type not in ("kpi",)
        st.plotly_chart(fig, width="stretch", theme=None, key=chart_key(spec),
                        on_select="rerun" if selectable else "ignore",
                        selection_mode=("points", "box", "lasso") if spec.type == "scatter" else ("points",),
                        config={"displaylogo": False})


def settings_panel(spec: V.VisualSpec, df, filtered, kinds):
    st.markdown(f"### {V.ICONS.get(spec.type, '')} Visual settings")
    cats = columns_of(kinds, df, ("country", "category", "date", "year", "text"))
    nums = columns_of(kinds, df, ("number",))

    def pick(label, name, options, current, fmt=None, help=None, allow_none=False):
        opts = ([None] if allow_none else []) + list(options)
        seed(vkey(spec, name), current if current in opts else (opts[0] if opts else None))
        return st.selectbox(label, opts, key=vkey(spec, name), format_func=fmt or (lambda o: "—" if o is None else str(o)),
                            help=help)

    kind = pick("Chart type", "type", list(V.TYPES), spec.type, fmt=lambda t: f"{V.ICONS[t]} {V.TYPES[t]}")
    if kind != spec.type:
        spec.type = kind
    seed(vkey(spec, "title"), spec.title)
    spec.title = st.text_input("Title", key=vkey(spec, "title"), placeholder=V.auto_title(spec))
    seed(vkey(spec, "subtitle"), spec.subtitle)
    spec.subtitle = st.text_input("Subtitle", key=vkey(spec, "subtitle"), placeholder="e.g. JD thousand · 2025")

    st.markdown("**Fields**")
    if kind == "kpi":
        spec.category = pick("Compare with last year using", "cat", columns_of(kinds, df, ("date", "year")),
                             spec.category, allow_none=True, help="A date / year column: shows the change on last year")
    else:
        label = {"scatter": "Points (one per)", "donut": "Slices", "treemap": "Boxes", "map": "Countries",
                 "flowmap": "Countries"}.get(kind, "Axis / category")
        cat = pick(label, "cat", cats, spec.category)
        if cat != spec.category:
            spec.category, spec.level, spec.path = cat, None, []
    a, b = st.columns([1.4, 1])
    seed(vkey(spec, "value"), spec.value if spec.value in nums else ROWS)
    value = a.selectbox("Value" if kind != "scatter" else "Y value", [ROWS, *nums], key=vkey(spec, "value"))
    spec.value = None if value == ROWS else value
    seed(vkey(spec, "agg"), spec.agg)
    spec.agg = b.selectbox("Measure", list(AGG_NAMES), format_func=AGG_NAMES.get, key=vkey(spec, "agg"),
                           disabled=spec.value is None)
    none = lambda o: "—" if o is None else str(o)  # noqa: E731
    if kind == "scatter" and nums:
        a, b = st.columns(2)
        seed(vkey(spec, "x"), spec.x_value if spec.x_value in nums else nums[min(1, len(nums) - 1)])
        spec.x_value = a.selectbox("X value", nums, key=vkey(spec, "x"))
        seed(vkey(spec, "size"), spec.size if spec.size in nums else None)
        spec.size = b.selectbox("Bubble size", [None, *nums], format_func=none, key=vkey(spec, "size"))
    if kind in V.MULTI:
        options = [None, *[c for c in cats if c != spec.category]]
        if S.get(vkey(spec, "legend")) not in options:   # the axis changed: the old legend may be gone
            S.pop(vkey(spec, "legend"), None)
        seed(vkey(spec, "legend"), spec.legend if spec.legend in options else None)
        spec.legend = st.selectbox("Legend (one series per value)", options, format_func=none, key=vkey(spec, "legend"))
    if kind == "flowmap":
        seed(vkey(spec, "hub"), spec.hub)
        spec.hub = st.text_input("Centre country", key=vkey(spec, "hub"))

    levels = V.hierarchy(spec, kinds)
    if levels and kind != "kpi":
        current_level = V.level_of(filtered, spec, kinds)
        lvl = st.segmented_control("Level", levels, default=current_level, key=vkey(spec, f"level-{len(spec.path)}"),
                                   format_func=lambda l: V.LEVEL_NAMES[l],
                                   help="Year › Quarter › Month › Date, or Region › Country")
        if lvl and lvl != current_level:
            V.set_level(spec, lvl)
            st.rerun()

    if kind not in ("kpi",):
        st.markdown("**Order and size**")
        a, b = st.columns(2)
        seed(vkey(spec, "sort"), spec.sort)
        spec.sort = a.selectbox("Sort", list(V.SORTS), format_func=V.SORTS.get, key=vkey(spec, "sort"))
        seed(vkey(spec, "top"), int(spec.top_n or 0))
        top = b.number_input("Top N (0 = all)", min_value=0, max_value=500, step=1, key=vkey(spec, "top"))
        spec.top_n = int(top) or None
        if spec.top_n:
            seed(vkey(spec, "other"), spec.other)
            spec.other = st.toggle("Add the rest up as “Other”", key=vkey(spec, "other"))
        a, b = st.columns([1.6, 1])
        seed(vkey(spec, "quick"), spec.quick)
        spec.quick = a.selectbox("Quick calculation", list(QUICK_NAMES), format_func=QUICK_NAMES.get,
                                 key=vkey(spec, "quick"), help="% of total, change on last year, running total, rank, "
                                                                 "moving average")
        if spec.quick == "moving_avg":
            seed(vkey(spec, "window"), spec.window)
            spec.window = int(b.number_input("Window", min_value=2, max_value=24, key=vkey(spec, "window")))
        if kind in ("bar", "hbar"):
            seed(vkey(spec, "hi"), spec.highlight)
            spec.highlight = b.selectbox("Highlight", list(HIGHLIGHTS), format_func=HIGHLIGHTS.get, key=vkey(spec, "hi"))

    with st.expander("🔎 Filters for this visual only", expanded=F.is_active(spec.filters)):
        render_group(spec.filters, df, kinds, depth=0, advanced=False, add_here=True)
    st.button("Done", on_click=select_visual, args=(spec.id,), width="stretch")


def report_tab(df, filtered, kinds):
    S.setdefault("visuals", [])
    S.setdefault("grid", 2)
    S.setdefault("selection", None)
    S.setdefault("sel_seen", {})
    S.setdefault("sel_gen", 0)
    if S.selection and not any(v.id == S.selection["visual"] for v in S.visuals):
        S.selection = None
    process_clicks(filtered, kinds)
    bar = st.columns([1.2, 1.4, 3, 1.6], vertical_alignment="center")
    bar[0].button("＋ Add visual", on_click=add_visual, type="primary", width="stretch")
    if bar[1].button("✨ Suggest for me", width="stretch", help="Chart ideas for the filtered data (cv.suggest)"):
        with st.spinner("Looking at the data…"):
            S.suggestions = [s.to_dict() for s in V.suggest(filtered.head(20000))]
    S.grid = bar[3].segmented_control("Columns", [1, 2, 3], default=S.grid, key="grid-cols",
                                      format_func=lambda n: f"{n} col", label_visibility="collapsed") or S.grid
    if S.get("suggestions"):
        with st.container(border=True):
            top = st.columns([6, 1])
            top[0].markdown("**✨ Suggested for the filtered data** · click to add")
            if top[1].button("Close", key="sug-close", type="tertiary"):
                S.suggestions = []
                st.rerun()
            cols = st.columns(4)
            for i, sd in enumerate(S.suggestions):
                sp = V.VisualSpec.from_dict(sd)
                cols[i % 4].button(f"{V.ICONS.get(sp.type, '')} {sp.title or V.auto_title(sp)}", key=f"sug-{i}",
                                   on_click=add_suggested, args=(sd,), width="stretch",
                                   help=f"{V.TYPES[sp.type]}: {sp.value or 'rows'} by {sp.category}")
    if not S.visuals:
        st.info("No visuals yet: click **＋ Add visual** or **✨ Suggest for me**.")
        return
    sel_row = st.columns([5, 1.3, 1.7], vertical_alignment="center")
    if S.selection:
        rows = int(V.selection_mask(filtered, S.selection).sum())
        sel_row[0].markdown(f"<div class='cs-count'>🎯 Selected in <b>{S.selection['title']}</b>: "
                            f"{V.describe_selection(S.selection)} · the other visuals show {rows:,} rows</div>",
                            unsafe_allow_html=True)
        sel_row[1].button("✕ Clear selection", on_click=clear_selection, width="stretch")
    else:
        sel_row[0].markdown("<span class='cs-muted'>Click a bar, slice, point or country to filter the other "
                            "visuals.</span>", unsafe_allow_html=True)
    sel_row[2].toggle("Click drills down", key="click_drill",
                      help="On: clicking a bar of a chart with levels (Year › Quarter › Month, Region › Country) "
                           "opens it instead of filtering the other visuals")
    selected = next((v for v in S.visuals if v.id == S.get("selected")), None)
    canvas, panel = (st.columns([2.6, 1.15], gap="medium") if selected else (st.container(), None))
    with canvas:
        n = max(1, S.grid - 1) if selected else S.grid     # the settings panel takes room: one column less
        grid = st.columns(n, gap="small")
        for i, spec in enumerate(S.visuals):
            with grid[i % n]:
                visual_card(spec, data_for(spec, filtered), kinds)
    if selected:
        with panel:
            with st.container(border=True):
                settings_panel(selected, df, filtered, kinds)


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
    data_t, report_t = st.tabs(["📁 Data", "📊 Report"])
    with data_t:
        data_tab(df, kinds, filtered)
    with report_t:
        if df is None:
            st.info("Load data first.")
        else:
            report_tab(df, filtered, kinds)


main()
