"""Designs ("themes"). Pick one with design="navy_gold", or build your own with make_design()."""
from __future__ import annotations

from dataclasses import dataclass, field, replace

# Categorical order for charts with several series (validated for colour-blind
# separation between neighbours). Themes may override it.
DEFAULT_SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]


@dataclass
class Design:
    name: str
    dark: bool
    background: tuple                 # (top, bottom) gradient, or (color, color) for flat
    map_style: str = "solid"          # "solid", "dots" or "none"
    map_color: str = "#ffffff"
    map_alpha: float = 0.06
    title_font: str = "serif"         # "serif" or "sans"
    title_color: str = "#f3d58a"
    subtitle_color: str = "#c9d1e0"
    text_color: str = "#d9dee8"       # labels
    muted_color: str = "#9aa6bb"      # ticks, source line
    axis_color: str = "#d4a84b"       # baseline
    grid_color: str = "#ffffff"
    grid_alpha: float = 0.07
    accent: str = "#d4a84b"           # title underline, highlights, trend lines
    bar: tuple = ("#081530", "#3f5f95")          # (bottom, top) gradient of normal bars
    highlight: tuple = ("#5a3a0a", "#f3d58a")    # (bottom, top) gradient of the highlighted bar
    bar_cap: str = "#d4a84b"          # thin line on top of each bar ("" for none)
    highlight_cap: str = "#f3d58a"
    rounded: bool = False
    shadow: bool = False
    glow: bool = True                 # soft glow behind the highlighted bar
    value_color: str = "#ffffff"
    highlight_value_color: str = "#f3d58a"
    icon_color: str = "#d4a84b"
    highlight_icon_color: str = "#0b1a3a"
    series: list = field(default_factory=lambda: list(DEFAULT_SERIES))
    sequential: tuple = ("#1d2f55", "#f3d58a")   # choropleth low -> high
    land_color: str = "#23365f"       # geo charts: countries without data
    border_color: str = "#0b1a3a"
    surface: str = "#0b1a3a"          # colour used for gaps between pie slices etc.
    card: str = "#132a52"             # KPI cards / legend boxes
    positive: str = "#3fbf7f"
    negative: str = "#ff6b6b"


DESIGNS: dict[str, Design] = {}


def _add(d: Design):
    DESIGNS[d.name] = d
    return d


# 1. Dark navy + gold (the first reference image)
_add(Design(name="navy_gold", dark=True, background=("#0b1a3a", "#050c1f"),
            series=["#f3d58a", "#5b8def", "#4fd1c5", "#e98c6b", "#b39ddb", "#81c995", "#f6c177", "#90a4ae"]))

# 2. Brighter blue background, same navy/gold bars
_add(Design(
    name="royal_blue", dark=True, background=("#4a86d0", "#1d4a8c"),
    map_color="#ffffff", map_alpha=0.10, grid_alpha=0.12, subtitle_color="#e6eefb",
    text_color="#eef3fb", muted_color="#d0dcef", land_color="#3a6db3", border_color="#2a5aa0",
    surface="#2a5aa0", card="#2a5aa0", sequential=("#9dbbe6", "#0b1a3a"),
    series=["#f3d58a", "#0b1a3a", "#ffffff", "#7fd1c7", "#f59e8b", "#b8a6ff", "#9ad06a", "#ffb347"],
))

# 3. Light grey + dotted map, teal bars, gold highlight (the second reference image)
_add(Design(
    name="ivory_dots", dark=False, background=("#f7f7f7", "#e9e9e9"),
    map_style="dots", map_color="#cfcfcf", map_alpha=0.75,
    title_font="sans", title_color="#1f3d4a", subtitle_color="#555555",
    text_color="#2b2b2b", muted_color="#666666", axis_color="#9a9a9a",
    grid_color="#bdbdbd", grid_alpha=0.6, accent="#b8862e",
    bar=("#0b2233", "#2f6272"), highlight=("#7a4a12", "#e6c15a"),
    bar_cap="", highlight_cap="", rounded=True, shadow=True, glow=False,
    value_color="#111111", highlight_value_color="#111111",
    icon_color="#e6c15a", highlight_icon_color="#ffffff",
    sequential=("#dfe8ea", "#0b2233"), land_color="#dcdcdc", border_color="#f4f4f4",
    surface="#f2f2f2", card="#ffffff",
    series=["#1f4e5f", "#c99a3b", "#5b8fa3", "#8c3b3b", "#7a9a5a", "#6b5b95", "#d08c60", "#3f3f3f"],
))

# 4. Deep green + gold
_add(Design(
    name="emerald_gold", dark=True, background=("#0d3b2e", "#051a14"),
    map_color="#ffffff", map_alpha=0.05, subtitle_color="#cfe3da", text_color="#e3efe9",
    muted_color="#9fbfb2", bar=("#06271e", "#2f7a61"), land_color="#1c4d3e",
    border_color="#0a2a21", surface="#082a20", card="#12443a", icon_color="#d4a84b",
    highlight_icon_color="#0d3b2e", sequential=("#1c4d3e", "#f3d58a"),
    series=["#f3d58a", "#4fd1a5", "#8ecae6", "#f28482", "#cdb4db", "#ffd166", "#90be6d", "#f9844a"],
))

# 5. Warm sand + dotted map, burgundy bars, gold highlight
_add(Design(
    name="desert_sand", dark=False, background=("#f8f1e5", "#eadcc4"),
    map_style="dots", map_color="#d8c6a6", map_alpha=0.8,
    title_font="serif", title_color="#5a1f24", subtitle_color="#6b5a4a",
    text_color="#3b2f25", muted_color="#7a6a58", axis_color="#a08a6a",
    grid_color="#b9a384", grid_alpha=0.45, accent="#b8862e",
    bar=("#3d0f14", "#8c2f39"), highlight=("#7a4a12", "#e6c15a"),
    bar_cap="", highlight_cap="", rounded=True, shadow=True, glow=False,
    value_color="#3b2f25", highlight_value_color="#3b2f25",
    icon_color="#e6c15a", highlight_icon_color="#5a1f24",
    sequential=("#f1e4cc", "#5a1f24"), land_color="#e3d3b6", border_color="#f8f1e5",
    surface="#f3e9d7", card="#fffaf1",
    series=["#8c2f39", "#c99a3b", "#3f6e5a", "#4b5d8c", "#d08c60", "#6b5b95", "#7a9a5a", "#3b2f25"],
))

# 6. Clean white report style
_add(Design(
    name="minimal", dark=False, background=("#ffffff", "#ffffff"), map_style="none",
    title_font="sans", title_color="#111827", subtitle_color="#4b5563",
    text_color="#1f2937", muted_color="#6b7280", axis_color="#9ca3af",
    grid_color="#e5e7eb", grid_alpha=1.0, accent="#2a78d6",
    bar=("#94a3b8", "#94a3b8"), highlight=("#2a78d6", "#2a78d6"),
    bar_cap="", highlight_cap="", rounded=True, shadow=False, glow=False,
    value_color="#111827", highlight_value_color="#111827",
    icon_color="#ffffff", highlight_icon_color="#ffffff",
    sequential=("#e3eefb", "#1b4f91"), land_color="#eef0f3", border_color="#ffffff",
    surface="#ffffff", card="#f5f7fa",
))

# 8. The trade report look: white, navy title, gold underline, slate bars, gold highlight
_add(Design(
    name="report_slate", dark=False, background=("#ffffff", "#ffffff"), map_style="none",
    title_font="sans", title_color="#1f3a5f", subtitle_color="#6b7280",
    text_color="#1f2937", muted_color="#6b7280", axis_color="#d1d5db",
    grid_color="#e5e7eb", grid_alpha=1.0, accent="#d9a92a",
    bar=("#5f7a88", "#5f7a88"), highlight=("#d9a92a", "#d9a92a"),
    bar_cap="", highlight_cap="", rounded=False, shadow=False, glow=False,
    value_color="#1f2937", highlight_value_color="#1f2937",
    icon_color="#ffffff", highlight_icon_color="#ffffff",
    sequential=("#e8eef2", "#1f3a5f"), land_color="#eef0f3", border_color="#ffffff",
    surface="#ffffff", card="#f5f7fa",
    series=["#5f7a88", "#d9a92a", "#1f3a5f", "#3f7f5a", "#b84a45", "#7a6ab0", "#8fa9b5", "#e0c26a"],
))

# 7. Charcoal + teal
_add(Design(
    name="charcoal_teal", dark=True, background=("#23272f", "#15181d"),
    map_color="#ffffff", map_alpha=0.05, title_font="sans", title_color="#ffffff",
    subtitle_color="#b8c0cc", text_color="#e6e9ee", muted_color="#9aa3af",
    axis_color="#4fd1c5", accent="#4fd1c5", bar=("#1b2a33", "#3f5866"),
    highlight=("#0f6b63", "#4fd1c5"), bar_cap="#4fd1c5", highlight_cap="#9ff5ec",
    value_color="#ffffff", highlight_value_color="#4fd1c5",
    icon_color="#4fd1c5", highlight_icon_color="#15181d",
    sequential=("#2c3440", "#4fd1c5"), land_color="#2c3440", border_color="#15181d",
    surface="#1b1f25", card="#2a3039",
    series=["#4fd1c5", "#f6ad55", "#90cdf4", "#fc8181", "#b794f4", "#f6e05e", "#68d391", "#fbb6ce"],
))


def get_design(design) -> Design:
    if isinstance(design, Design):
        return design
    if design not in DESIGNS:
        raise ValueError(f"Unknown design '{design}'. Available: {', '.join(DESIGNS)}")
    return DESIGNS[design]


def make_design(name: str, base: str = "navy_gold", **changes) -> Design:
    """Create and register your own design, e.g.
    make_design("chamber", base="navy_gold", accent="#c8102e", highlight=("#7a0a18", "#e0313f"))
    """
    d = replace(get_design(base), name=name, **changes)
    DESIGNS[name] = d
    return d


def list_designs() -> list[str]:
    return list(DESIGNS)
