"""Upload app: drop an Excel file, get chart suggestions, style them, download.

Run with:   python -m chamberviz app      (or: streamlit run chamberviz/app.py)
"""
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

import chamberviz as cv

st.set_page_config(page_title="Chart studio", layout="wide")

TMP = Path(tempfile.gettempdir()) / "chamberviz_app"
TMP.mkdir(exist_ok=True)


def show_image(png):
    try:
        st.image(png, width="stretch")
    except Exception:  # older Streamlit
        st.image(png, use_container_width=True)


def save_upload(f, name=None) -> Path:
    p = TMP / (name or f.name)
    p.write_bytes(f.getbuffer())
    return p


# ------------------------------------------------------------------ sidebar: style
with st.sidebar:
    st.header("Design")
    design = st.selectbox("Design", cv.list_designs())
    size = st.selectbox("Figure size", ["16 x 9 (slides)", "12 x 8", "10 x 10 (square)", "8 x 10 (portrait)"])
    figure_size = {"16 x 9 (slides)": (16, 9), "12 x 8": (12, 8), "10 x 10 (square)": (10, 10),
                   "8 x 10 (portrait)": (8, 10)}[size]
    st.header("Logo")
    logo_file = st.file_uploader("Logo (PNG/JPG). Empty = your saved default", type=["png", "jpg", "jpeg"])
    logo_alignment = st.selectbox("Logo position", ["top-right", "top-left", "bottom-right", "bottom-left"])
    no_logo = st.checkbox("No logo")
    logo_size = st.slider("Logo size", 0.05, 0.2, 0.10, 0.01)
    st.header("Background")
    bg_map = st.selectbox("World map behind the chart", ["design default", "solid", "dots", "none"])
    use_bg_color = st.checkbox("Custom background colour")
    bg1 = st.color_picker("Top colour", "#0b1a3a", disabled=not use_bg_color)
    bg2 = st.color_picker("Bottom colour", "#050c1f", disabled=not use_bg_color)
    bg_img = st.file_uploader("Background image", type=["png", "jpg", "jpeg"])
    bg_op = st.slider("Background image strength", 0.05, 1.0, 0.35, 0.05, disabled=bg_img is None)
    st.header("Text")
    source = st.text_input("Source line", "")

style = {"design": design, "figure_size": figure_size, "logo_alignment": logo_alignment,
         "logo_size": logo_size}
if no_logo:
    style["logo"] = None
elif logo_file is not None:
    style["logo"] = str(save_upload(logo_file, "logo_" + logo_file.name))
if bg_map != "design default":
    style["background_map"] = False if bg_map == "none" else bg_map
if use_bg_color:
    style["background_color"] = (bg1, bg2)
if bg_img is not None:
    style["background_image"] = str(save_upload(bg_img, "bg_" + bg_img.name))
    style["background_image_opacity"] = bg_op
if source:
    style["source"] = source

# ------------------------------------------------------------------ main
st.title("Chart studio")
up = st.file_uploader("Upload an Excel or CSV file", type=["xlsx", "xls", "csv"])
if up is None:
    st.info("Upload a file to get chart suggestions. Try examples/sample_trade_data.xlsx.")
    st.stop()

path = save_upload(up)
sheets = cv.read_excel(path)
sheet = st.selectbox("Sheet", list(sheets))
df = sheets[sheet]
with st.expander(f"Data ({len(df)} rows, cleaned)", expanded=False):
    st.dataframe(df)
    info = cv.analyze(df)[0]
    st.caption(" · ".join(f"**{c.name}**: {c.kind}" for c in info.columns))

tab_auto, tab_manual = st.tabs(["Suggested charts", "Build my own"])

with tab_auto:
    sugs = [s for s in cv.suggest(path, sheet=sheet, verbose=False)]
    if not sugs:
        st.warning("No suggestions: the sheet needs at least one numeric column.")
    else:
        labels = [f"{s.score:.0f} · {s.name} · {s.title}" for s in sugs]
        i = st.radio("Pick a suggestion (best first)", range(len(sugs)), format_func=lambda k: labels[k])
        s = sugs[i]
        st.caption(f"Why: {s.reason}")
        c1, c2 = st.columns(2)
        title = c1.text_input("Title", s.title, key=f"t{i}{sheet}")
        subtitle = c2.text_input("Subtitle", s.kwargs.get("subtitle", ""), key=f"s{i}{sheet}")
        try:
            chart = s.render(**style, title=title, subtitle=subtitle or None)
            png = chart.to_bytes(dpi=200)
            show_image(png)
            d1, d2, _ = st.columns([1, 1, 3])
            d1.download_button("Download PNG", png, file_name=f"{s.chart}.png", mime="image/png")
            d2.download_button("Download PDF", chart.to_bytes("pdf"), file_name=f"{s.chart}.pdf",
                               mime="application/pdf")
            chart.close()
            st.code(s.code(design=design).replace(str(path), up.name), language="python")
        except Exception as e:  # show the problem instead of crashing the app
            st.error(f"Could not draw this chart: {e}")

with tab_manual:
    kinds = {"Bar": "bar", "Horizontal bar": "barh", "Donut / pie": "pie", "Line": "line",
             "Area": "area", "Dot / lollipop": "dot", "Treemap": "treemap", "Map (countries)": "geo",
             "Flow map into Jordan": "flow", "Histogram": "hist", "Box plot": "box", "Scatter": "scatter"}
    k = st.selectbox("Chart type", list(kinds))
    kind = kinds[k]
    cols = list(df.columns)
    nums = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
    c1, c2 = st.columns(2)
    xcol = c1.selectbox("Labels / X column", cols) if kind not in ("hist",) else None
    ycol = c2.selectbox("Values / Y column", nums) if nums else None
    title = st.text_input("Title", f"{ycol} by {xcol}" if xcol else str(ycol))
    subtitle = st.text_input("Subtitle ", "")
    extra = {}
    if kind in ("bar", "barh", "dot", "treemap"):
        extra["sort"] = "desc" if st.checkbox("Sort largest first", True) else None
        if kind in ("bar", "barh"):
            extra["icons"] = "auto" if st.checkbox("Add icons (guessed from labels)") else None
    if ycol is None:
        st.warning("This sheet has no numeric column.")
        st.stop()
    try:
        common = dict(style, title=title, subtitle=subtitle or None)
        data = df.dropna(subset=[ycol])
        if kind in ("bar", "barh"):
            g = data.groupby(xcol, sort=False)[ycol].sum()
            ch = cv.barplot(g, horizontal=kind == "barh", **extra, **common)
        elif kind == "pie":
            ch = cv.pieplot(data.groupby(xcol, sort=False)[ycol].sum(), **common)
        elif kind in ("line", "area"):
            g = data.groupby(xcol, sort=True)[ycol].sum()
            ch = cv.lineplot(list(g.index), list(g.values), area=kind == "area", **common)
        elif kind == "dot":
            ch = cv.dotplot(data.groupby(xcol, sort=False)[ycol].sum(), **extra, **common)
        elif kind == "treemap":
            extra.pop("sort", None)
            ch = cv.treemap(data.groupby(xcol, sort=False)[ycol].sum(), **common)
        elif kind == "geo":
            ch = cv.geoplot(data.groupby(xcol, sort=False)[ycol].sum(), **common)
        elif kind == "flow":
            ch = cv.flowmap(data.groupby(xcol, sort=False)[ycol].sum(), **common)
        elif kind == "hist":
            ch = cv.histplot(data[ycol], xlabel=ycol, **common)
        elif kind == "box":
            ch = cv.boxplot(data, x=xcol, y=ycol, **common)
        else:
            ch = cv.scatterplot(data, x=xcol, y=ycol, **common)
        png = ch.to_bytes(dpi=200)
        show_image(png)
        st.download_button("Download PNG", png, file_name=f"{kind}.png", mime="image/png")
        ch.close()
    except Exception as e:
        st.error(f"Could not draw this chart: {e}")
