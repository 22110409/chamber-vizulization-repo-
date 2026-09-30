"""Plotly templates made from the chamberviz designs, so the interactive charts in the app look
like the branded exports (same background, text colours, series colours, gold highlight, fonts).

    import plotly.express as px
    from chamberstudio.plotly_theme import template, highlight_colors
    fig = px.bar(df, x="Country", y="Value", template=template("navy_gold"))
    fig.update_traces(marker_color=highlight_colors("navy_gold", values))   # largest bar in gold
"""
from __future__ import annotations

from functools import lru_cache

import plotly.graph_objects as go
import plotly.io as pio
from matplotlib.colors import to_hex, to_rgb

import chamberviz as cv
from chamberviz.themes import get_design

# Browsers may not have the chamberviz fonts installed: fall back to close system fonts.
SANS = "'Noto Sans', 'Noto Sans Arabic', 'Segoe UI', Tahoma, Arial, sans-serif"
SERIF = "'Noto Serif Display', 'Amiri', Georgia, 'Times New Roman', serif"


def _rgba(color: str, alpha: float) -> str:
    r, g, b = (int(round(c * 255)) for c in to_rgb(color))
    return f"rgba({r},{g},{b},{alpha:.2f})"


def _mix(a: str, b: str, t: float = 0.5) -> str:
    ra, rb = to_rgb(a), to_rgb(b)
    return to_hex(tuple(x * (1 - t) + y * t for x, y in zip(ra, rb)))


@lru_cache(maxsize=None)
def template(design: str) -> go.layout.Template:
    """A Plotly template for a chamberviz design (also registered as pio.templates['cv_<design>'])."""
    d = get_design(design)
    top, bottom = d.background
    bg = _mix(top, bottom)          # Plotly has no gradient background: the middle of the design's gradient
    grid = _rgba(d.grid_color, min(1.0, d.grid_alpha * (2.2 if d.dark else 1.0)))
    axis = dict(gridcolor=grid, linecolor=d.axis_color, zerolinecolor=_rgba(d.axis_color, 0.6),
                tickfont=dict(color=d.muted_color, family=SANS, size=12),
                title=dict(font=dict(color=d.muted_color, family=SANS, size=13)), showline=True, ticks="")
    t = go.layout.Template()
    t.layout = go.Layout(
        paper_bgcolor=bg, plot_bgcolor=bg,
        font=dict(family=SANS, color=d.text_color, size=13),
        title=dict(font=dict(family=SERIF if d.title_font == "serif" else SANS, color=d.title_color, size=20),
                   x=0.5, xanchor="center"),
        colorway=list(d.series),
        xaxis={**axis, "showgrid": False}, yaxis={**axis, "showline": False},   # like chamberviz: no vertical grid
        legend=dict(font=dict(color=d.text_color, family=SANS), bgcolor="rgba(0,0,0,0)", orientation="h",
                    yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        hoverlabel=dict(bgcolor=d.card, font=dict(color=d.text_color, family=SANS), bordercolor=d.accent),
        colorscale=dict(sequential=[[0, d.sequential[0]], [1, d.sequential[1]]]),
        geo=dict(bgcolor=bg, landcolor=d.land_color, showland=True, showcountries=True,
                 countrycolor=d.border_color, coastlinecolor=d.border_color, showframe=False,
                 lakecolor=bg, showlakes=False),
        margin=dict(l=40, r=24, t=70, b=40),
    )
    t.data.bar = [go.Bar(marker=dict(color=d.bar[1], line=dict(width=0)))]
    t.data.pie = [go.Pie(marker=dict(colors=list(d.series), line=dict(color=d.surface, width=2)))]
    t.data.scatter = [go.Scatter(line=dict(width=3), marker=dict(size=8))]
    t.data.treemap = [go.Treemap(marker=dict(colors=list(d.series)))]
    pio.templates[f"cv_{design}"] = t
    return t


def apply(fig: go.Figure, design: str) -> go.Figure:
    """Give a figure the design: its template, plus the colours set on the figure itself (Streamlit
    replaces the backgrounds coming only from a template)."""
    t = template(design)
    lay = t.layout
    fig.update_layout(template=t, paper_bgcolor=lay.paper_bgcolor, plot_bgcolor=lay.plot_bgcolor,
                      font=lay.font, title_font=lay.title.font, colorway=lay.colorway,
                      legend=dict(font=lay.legend.font, bgcolor=lay.legend.bgcolor),
                      hoverlabel=lay.hoverlabel)
    fig.update_xaxes(showgrid=False, gridcolor=lay.xaxis.gridcolor, linecolor=lay.xaxis.linecolor, tickfont=lay.xaxis.tickfont,
                     zerolinecolor=lay.xaxis.zerolinecolor)
    fig.update_yaxes(gridcolor=lay.yaxis.gridcolor, linecolor=lay.yaxis.linecolor, tickfont=lay.yaxis.tickfont,
                     zerolinecolor=lay.yaxis.zerolinecolor)
    if fig.layout.geo is not None:
        fig.update_geos(bgcolor=lay.geo.bgcolor, landcolor=lay.geo.landcolor, countrycolor=lay.geo.countrycolor)
    return fig


def colors(design: str) -> dict:
    """The design colours the app needs by name."""
    d = get_design(design)
    return {"bar": d.bar[1], "highlight": d.highlight[1], "accent": d.accent, "text": d.text_color,
            "title": d.title_color, "muted": d.muted_color, "background": _mix(*d.background), "card": d.card,
            "positive": d.positive, "negative": d.negative, "series": list(d.series), "dark": d.dark}


def highlight_colors(design: str, values, highlight: str | int | None = "max") -> list[str]:
    """One colour per bar: the design's bar colour, and the highlight colour on the largest
    ('max'), smallest ('min'), last ('last') or n-th bar."""
    c = colors(design)
    values = list(values)
    out = [c["bar"]] * len(values)
    if not values or highlight is None:
        return out
    if highlight == "max":
        i = max(range(len(values)), key=lambda k: values[k])
    elif highlight == "min":
        i = min(range(len(values)), key=lambda k: values[k])
    elif highlight == "last":
        i = len(values) - 1
    else:
        i = int(highlight)
    out[i] = c["highlight"]
    return out


def register_all() -> list[str]:
    """Build the template of every design (names: cv_<design>)."""
    for name in cv.list_designs():
        template(name)
    return [f"cv_{n}" for n in cv.list_designs()]
