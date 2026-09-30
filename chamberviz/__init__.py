"""chamberviz - branded charts in one line, plus automatic chart suggestions from Excel.

Simple version (you choose the chart):
    import chamberviz as cv
    cv.barplot(labels, values, design="navy_gold", title="...", logo_alignment="top-right",
               save="chart.png")

Dynamic version (it looks at your Excel file and suggests charts):
    cv.suggest("data.xlsx")                  # ranked chart ideas with reasons
    cv.auto("data.xlsx", out_dir="charts")   # draws them + an HTML report with the code
"""
__version__ = "1.0.0"

from .config import set_defaults, set_default_logo, DEFAULTS
from .themes import DESIGNS, Design, list_designs, make_design, get_design
from .assets_lookup import (country_code, country_info, country_name, all_countries, flag,
                            flag_path, search_icons, auto_icon, looks_like_countries)
from .canvas import Chart, COMMON_OPTIONS
from .charts_bar import barplot, multibarplot, dotplot, treemap
from .charts_stats import pieplot, lineplot, areaplot, histplot, boxplot, scatterplot, heatmap
from .charts_geo import geoplot, flowmap, REGIONS
from .charts_kpi import kpi_cards
from .gallery import preview_designs, icon_sheet, flag_sheet
from .suggest import (read_excel, analyze, suggest, Suggestion, apply_filters, filter_choices,
                      filter_columns)
from .auto import auto

# Friendly aliases
bar = barplot
pie = donut = pieplot
line = lineplot
hist = histplot
box = boxplot
scatter = scatterplot
dot = lollipop = dotplot
dumbbell = dotplot
geo = mapplot = geoplot
kpi = kpi_cards

CHART_TYPES = {
    "bar": barplot, "barh": barplot, "multibar": multibarplot, "stacked": multibarplot,
    "pie": pieplot, "donut": pieplot, "line": lineplot, "area": areaplot, "hist": histplot,
    "box": boxplot, "scatter": scatterplot, "dot": dotplot, "dumbbell": dotplot,
    "treemap": treemap, "heatmap": heatmap, "geo": geoplot, "flow": flowmap, "kpi": kpi_cards,
}


def options():
    """Print the options every chart accepts."""
    for k, v in COMMON_OPTIONS.items():
        print(f"  {k:<26} {v}")
