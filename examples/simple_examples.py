"""SIMPLE VERSION - you choose the chart and the design.

Run:  python examples/simple_examples.py      (charts are saved in ./my_charts)
"""
import chamberviz as cv

LOGO = "chamberviz/assets/logos/demo_logo.png"   # replace with your logo, or run cv.set_default_logo(...) once
OUT = "my_charts/"

countries = ["China", "Saudi Arabia", "United States", "UAE", "Germany", "Egypt", "Switzerland"]
imports = [4179.8, 2975.3, 1691.8, 1166.0, 718.2, 649.0, 593.9]

# 1) The style you described: every option in one call ------------------------------
cv.barplot(
    countries, imports,
    figure_size=(12, 8),
    design="navy_gold",                    # navy_gold, royal_blue, ivory_dots, emerald_gold,
                                           # desert_sand, minimal, charcoal_teal
    bars=None,                             # None = design colours | "#2f6272" | ("#081530", "#3f5f95") | a list
    background_color=None,                 # "#0b1a3a" or ("#top", "#bottom") for a gradient
    background_image=None,                 # "path/to/photo.jpg"
    logo=LOGO,
    logo_alignment=("top", "right"),       # top-right, top-left, bottom-right, bottom-left
    title="Top import sources 2025",
    subtitle="JD million",
    source="Source: Central Bank of Jordan (sample figures)",
    save=OUT + "01_bar.png",
)

# 2) Arabic works automatically (letters joined, right to left, flags found by Arabic name)
cv.barplot(["الصين الشعبية", "السعودية", "الولايات المتحدة", "الأمارات العربية", "المانيا", "مصر", "سويسرا"],
           imports, design="ivory_dots", title="أهم مصادر المستوردات 2025", subtitle="مليون دينار",
           source="المصدر: بيانات البنك المركزي (بيانات أولية)", logo=LOGO, save=OUT + "02_bar_arabic.png")

# 3) Icons: "auto" guesses from the labels, or give names (see cv.search_icons("truck"))
commodities = ["Mineral fuels", "Vehicles", "Pearls & gold", "Machinery", "Electrical equipment", "Cereals", "Plastics"]
values = [2668.2, 2209.4, 1713.9, 1549.4, 944.5, 727.3, 668.2]
cv.barplot(commodities, values, icons="auto", ylabel="JD million", title="Top import commodities 2025",
           logo=LOGO, save=OUT + "03_bar_icons.png")

# 4) Horizontal bars, right-to-left
cv.barplot(countries, imports, horizontal=True, design="desert_sand", title="Import sources",
           logo=LOGO, logo_alignment="top-left", save=OUT + "04_barh.png")

# 5) Donut
cv.pieplot(commodities, values, icons="auto", title="Import mix 2025", logo=LOGO, save=OUT + "05_donut.png")

# 6) Line over time (several series + % change)
years = [2019, 2020, 2021, 2022, 2023, 2024, 2025]
cv.lineplot(years, {"Imports": [13.8, 11.9, 14.9, 18.9, 18.5, 18.9, 19.4],
                    "Exports": [5.9, 5.7, 6.8, 9.1, 8.8, 8.9, 9.3]},
            show_change=True, design="charcoal_teal", title="Trade balance", subtitle="JD billion",
            logo=LOGO, save=OUT + "06_line.png")

# 7) Two years compared (dumbbell)
cv.dotplot(countries, imports, compare=[3890, 3120, 1502, 1031, 760, 601, 420], names=("2024", "2025"),
           design="ivory_dots", title="2024 vs 2025", logo=LOGO, save=OUT + "07_dumbbell.png")

# 8) Maps
cv.geoplot(countries, imports, title="Where imports come from", logo=LOGO, save=OUT + "08_map.png")
cv.geoplot(countries, imports, region="middle_east", design="ivory_dots", title="The region",
           logo=LOGO, save=OUT + "09_map_region.png")
cv.flowmap(countries, imports, hub="Jordan", title="Import flows into Jordan", logo=LOGO,
           save=OUT + "10_flows.png")

# 9) Treemap, KPI cards, grouped / stacked bars
cv.treemap(commodities, values, icons="auto", title="What Jordan imports", logo=LOGO, save=OUT + "11_treemap.png")
cv.kpi_cards([
    {"label": "Total imports", "value": 19400.5, "unit": "JD million", "change": 2.6, "icon": "package-import"},
    {"label": "Total exports", "value": 9300.2, "unit": "JD million", "change": 4.5, "icon": "package-export"},
    {"label": "Top partner", "value": "China", "flag": "China", "note": "21.5% of imports"},
], title="Trade at a glance 2025", logo=LOGO, save=OUT + "12_kpis.png")
cv.multibarplot(["Q1", "Q2", "Q3", "Q4"], {"2024": [4.4, 4.8, 4.6, 5.2], "2025": [4.9, 5.1, 5.0, 5.6]},
                design="royal_blue", title="Quarterly imports", subtitle="JD billion", logo=LOGO,
                save=OUT + "13_grouped.png")

# 10) From a DataFrame / Excel
import pandas as pd
df = pd.DataFrame({"Country": countries, "Value": imports})
cv.barplot(df, x="Country", y="Value", design="emerald_gold", title="From a DataFrame", logo=LOGO,
           save=OUT + "14_from_dataframe.png")

# 11) Your own design (brand colours)
cv.make_design("my_brand", base="navy_gold", accent="#c8102e", highlight=("#6d0a18", "#e0313f"),
               title_color="#ffffff", icon_color="#e0313f", bar_cap="#c8102e", highlight_cap="#ff6b7d")
cv.barplot(countries, imports, design="my_brand", title="Custom design", logo=LOGO, save=OUT + "15_custom_design.png")

print("Charts saved in", OUT)
