"""The standard test set: every chart type, in English and in Arabic, with realistic trade data.

Each case is a function taking the style options (design, figure_size, logo...) and returning a
chamberviz Chart. Numbers are sample figures for evaluation only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

import chamberviz as cv

COUNTRIES_EN = ["China", "Saudi Arabia", "United States", "UAE", "Germany", "Egypt", "Switzerland"]
COUNTRIES_AR = ["الصين الشعبية", "السعودية", "الولايات المتحدة", "الأمارات العربية", "المانيا", "مصر", "سويسرا"]
IMPORTS = [4179.8, 2975.3, 1691.8, 1166.0, 718.2, 649.0, 593.9]
IMPORTS_2024 = [3890.0, 3120.0, 1502.0, 1031.0, 760.0, 601.0, 420.0]
EXPORTS = [410.5, 980.2, 2210.7, 640.3, 95.1, 310.8, 150.2]

GOODS_EN = ["Mineral fuels", "Vehicles", "Pearls & gold", "Machinery", "Electrical equipment", "Cereals", "Plastics"]
GOODS_AR = ["الوقود المعدني", "المركبات", "اللؤلؤ والذهب", "الآلات", "المعدات الكهربائية", "الحبوب", "اللدائن"]
GOODS_VALUES = [2668.2, 2209.4, 1713.9, 1549.4, 944.5, 727.3, 668.2]

YEARS = [2019, 2020, 2021, 2022, 2023, 2024, 2025]
IMPORTS_BN = [13.8, 11.9, 14.9, 18.9, 18.5, 18.9, 19.4]
EXPORTS_BN = [5.9, 5.7, 6.8, 9.1, 8.8, 8.9, 9.3]

QUARTERS_EN = ["Q1", "Q2", "Q3", "Q4"]
QUARTERS_AR = ["الربع الأول", "الربع الثاني", "الربع الثالث", "الربع الرابع"]
QUARTERLY = {"2024": [4.4, 4.8, 4.6, 5.2], "2025": [4.9, 5.1, 5.0, 5.6]}


@dataclass(frozen=True)
class Case:
    id: str
    name: str
    language: str          # "en" or "ar"
    draw: Callable         # draw(style: dict) -> chamberviz Chart


def _monthly():
    rng = np.random.default_rng(7)
    return rng.gamma(4.0, 120.0, 240)


def _heat():
    return pd.DataFrame({"2023": [3.1, 2.4, 1.9, 1.2], "2024": [3.4, 2.6, 1.7, 1.3], "2025": [3.9, 2.9, 1.6, 1.5]},
                        index=["China", "Saudi Arabia", "United States", "UAE"])


CASES = [
    # ------------------------------------------------------------------ English
    Case("bar_flags", "Bar · flags", "en", lambda s: cv.barplot(
        COUNTRIES_EN, IMPORTS, title="Top import sources 2025", subtitle="JD million",
        source="Source: sample figures", **s)),
    Case("bar_icons", "Bar · icons", "en", lambda s: cv.barplot(
        GOODS_EN, GOODS_VALUES, icons="auto", ylabel="JD million", title="Top import commodities 2025", **s)),
    Case("barh", "Horizontal bar", "en", lambda s: cv.barplot(
        COUNTRIES_EN, IMPORTS, horizontal=True, title="Import sources", subtitle="JD million", **s)),
    Case("grouped", "Grouped bars", "en", lambda s: cv.multibarplot(
        QUARTERS_EN, QUARTERLY, title="Quarterly imports", subtitle="JD billion", **s)),
    Case("stacked", "Stacked bars", "en", lambda s: cv.multibarplot(
        QUARTERS_EN, QUARTERLY, stacked=True, title="Quarterly imports, stacked", subtitle="JD billion", **s)),
    Case("donut", "Donut · icons", "en", lambda s: cv.pieplot(
        GOODS_EN, GOODS_VALUES, icons="auto", title="Import mix 2025", **s)),
    Case("line", "Lines · change", "en", lambda s: cv.lineplot(
        YEARS, {"Imports": IMPORTS_BN, "Exports": EXPORTS_BN}, show_change=True, title="Trade balance",
        subtitle="JD billion", **s)),
    Case("area", "Area", "en", lambda s: cv.lineplot(
        YEARS, IMPORTS_BN, area=True, title="Imports over time", subtitle="JD billion", **s)),
    Case("dumbbell", "Dumbbell 2024 vs 2025", "en", lambda s: cv.dotplot(
        COUNTRIES_EN, IMPORTS, compare=IMPORTS_2024, names=("2024", "2025"), title="2024 vs 2025", **s)),
    Case("treemap", "Treemap · icons", "en", lambda s: cv.treemap(
        GOODS_EN, GOODS_VALUES, icons="auto", title="What Jordan imports", **s)),
    Case("histogram", "Histogram", "en", lambda s: cv.histplot(
        _monthly(), xlabel="Shipment value (JD thousand)", title="Distribution of shipment values", **s)),
    Case("boxplot", "Box plot", "en", lambda s: cv.boxplot(
        {q: list(_monthly()[i * 60:(i + 1) * 60]) for i, q in enumerate(QUARTERS_EN)},
        title="Shipment values by quarter", **s)),
    Case("scatter", "Scatter · flags", "en", lambda s: cv.scatterplot(
        IMPORTS, EXPORTS, labels=COUNTRIES_EN, xlabel="Imports (JD million)", ylabel="Exports (JD million)",
        title="Imports vs exports by partner", **s)),
    Case("heatmap", "Heatmap", "en", lambda s: cv.heatmap(_heat(), title="Imports by partner and year", **s)),
    Case("map_world", "World map", "en", lambda s: cv.geoplot(
        COUNTRIES_EN, IMPORTS, title="Where imports come from", **s)),
    Case("map_region", "Middle East map", "en", lambda s: cv.geoplot(
        COUNTRIES_EN, IMPORTS, region="middle_east", title="The region", **s)),
    Case("flowmap", "Flow map into Jordan", "en", lambda s: cv.flowmap(
        COUNTRIES_EN, IMPORTS, hub="Jordan", title="Import flows into Jordan", **s)),
    Case("kpi", "KPI cards", "en", lambda s: cv.kpi_cards([
        {"label": "Total imports", "value": 19400.5, "unit": "JD million", "change": 2.6, "icon": "package-import"},
        {"label": "Total exports", "value": 9300.2, "unit": "JD million", "change": 4.5, "icon": "package-export"},
        {"label": "Top partner", "value": "China", "flag": "China", "note": "21.5% of imports"},
    ], title="Trade at a glance 2025", **s)),
    # ------------------------------------------------------------------ Arabic
    Case("bar_ar", "Bar · Arabic", "ar", lambda s: cv.barplot(
        COUNTRIES_AR, IMPORTS, title="أهم مصادر المستوردات 2025", subtitle="مليون دينار",
        source="المصدر: بيانات تجريبية", **s)),
    Case("barh_ar", "Horizontal bar · Arabic RTL", "ar", lambda s: cv.barplot(
        COUNTRIES_AR, IMPORTS, horizontal=True, rtl=True, title="مصادر المستوردات", subtitle="مليون دينار", **s)),
    Case("grouped_ar", "Grouped bars · Arabic", "ar", lambda s: cv.multibarplot(
        QUARTERS_AR, QUARTERLY, title="المستوردات الفصلية", subtitle="مليار دينار", **s)),
    Case("donut_ar", "Donut · Arabic", "ar", lambda s: cv.pieplot(
        GOODS_AR, GOODS_VALUES, title="هيكل المستوردات 2025", **s)),
    Case("line_ar", "Lines · Arabic", "ar", lambda s: cv.lineplot(
        YEARS, {"المستوردات": IMPORTS_BN, "الصادرات": EXPORTS_BN}, show_change=True, title="الميزان التجاري",
        subtitle="مليار دينار", **s)),
    Case("dumbbell_ar", "Dumbbell · Arabic", "ar", lambda s: cv.dotplot(
        COUNTRIES_AR, IMPORTS, compare=IMPORTS_2024, names=("2024", "2025"), title="مقارنة 2024 و2025", **s)),
    Case("treemap_ar", "Treemap · Arabic", "ar", lambda s: cv.treemap(
        GOODS_AR, GOODS_VALUES, title="ماذا يستورد الأردن", **s)),
    Case("map_ar", "World map · Arabic", "ar", lambda s: cv.geoplot(
        COUNTRIES_AR, IMPORTS, title="من أين تأتي المستوردات", **s)),
    Case("flowmap_ar", "Flow map · Arabic", "ar", lambda s: cv.flowmap(
        COUNTRIES_AR, IMPORTS, hub="Jordan", title="تدفقات المستوردات إلى الأردن", **s)),
    Case("kpi_ar", "KPI cards · Arabic", "ar", lambda s: cv.kpi_cards([
        {"label": "إجمالي المستوردات", "value": 19400.5, "unit": "مليون دينار", "change": 2.6, "icon": "package-import"},
        {"label": "إجمالي الصادرات", "value": 9300.2, "unit": "مليون دينار", "change": 4.5, "icon": "package-export"},
        {"label": "الشريك الأول", "value": "الصين", "flag": "China", "note": "21.5% من المستوردات"},
    ], title="التجارة في لمحة 2025", **s)),
]

BY_ID = {case.id: case for case in CASES}
