"""ACC trade charts: a fixed set of charts from the cleaned foreign-trade dataset
(arabic_cleaned_trade_data_ar_full_2023_2025.xlsx or a CSV with the same columns), drawn in four
designs and in Arabic and English. Each section offers two to four chart ideas to choose from.

    python reports/acc_trade_charts.py                         # default data file, everything
    python reports/acc_trade_charts.py data.xlsx --lang ar --designs navy_gold report_slate
    python reports/acc_trade_charts.py --only overview blocs   # some sections only

Output: reports/output/acc_trade_charts/<lang>/<design>/<chart>.png, one PDF per language and
design, and index.html to compare every option side by side.

The data has one row per trade type (Export = national exports, Re-Export, Import) x country x
commodity x year, value in JD. The newest year in the file is the report year and the year
before it the comparison year, so next year's file needs no change here.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import pandas as pd  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

import chamberviz as cv  # noqa: E402
from chamberviz.assets_lookup import country_code, country_name  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# ============================================================== settings (edit here)
DATA = Path(r"C:\Users\ixiat\Desktop\ACC AI Platform\ACC-AI\workflows\data\trading\final_trade_reports"
            r"\2025_vs_2024\runs\run_20260916_125931\input_excels\arabic_cleaned_trade_data_ar_full_2023_2025.xlsx")
DATA_EN = DATA.with_name("english_cleaned_trade_data_en_full_2023_2025.xlsx")   # only for commodity names
OUT = HERE / "output" / "acc_trade_charts"
DESIGNS = ["charcoal_teal", "royal_blue", "navy_gold", "report_slate"]
LANGS = ["ar", "en"]
TOP = 7                         # bars in the "top" charts
MILLION = 1e6                   # the data is in JD: charts show JD million
SIZE = (12, 6.75)
DPI = 160
FOCUS = ["الأسمدة", "الألبسة وتوابعها", "محضرات الصيدلة", "الوقود والزيوت المعدنية"]   # section 8

# Arabic names the country list does not know -> ISO code
COUNTRY_FIX = {"تشيكو": "CZ", "قازخستان": "KZ", "الدومنيكان": "DO", "جامبيا": "GM", "قرغيرستان": "KG",
               "لشتنستاين": "LI", "يوغسلافيا": "RS", "ارتيريا": "ER", "ريونيون": "RE"}
# short names for charts (others come from chamberviz's country list)
SHORT = {"ar": {"SA": "السعودية", "AE": "الإمارات", "PS": "فلسطين", "US": "الولايات المتحدة", "CN": "الصين",
                "GB": "المملكة المتحدة", "KR": "كوريا الجنوبية", "SY": "سوريا", "RU": "روسيا"},
         "en": {"SA": "Saudi Arabia", "AE": "UAE", "PS": "Palestine", "US": "USA", "CN": "China", "GB": "UK",
                "KR": "South Korea", "SY": "Syria", "RU": "Russia", "IR": "Iran"}}

# economic blocs (ISO codes); everything else is "other"
GAFTA = set("AE BH TN SA SD SY IQ OM PS QA KW LB LY EG MA YE DZ".split())
NAFTA = {"US", "CA", "MX"}
_REG = json.loads((ROOT / "chamberstudio" / "regions.json").read_text(encoding="utf-8"))["regions"]
EU = set(_REG["EU"]["countries"])
ASIA = set(_REG["Asia"]["countries"])      # non-Arab Asia, incl. Turkey and Israel (as in the tables)
BLOCS = {   # key: (Arabic, English, map region, colour in the bloc donut)
    "gafta": ("منطقة التجارة الحرة العربية الكبرى", "Greater Arab Free Trade Area", "arab_world", "#1f3a5f"),
    "asia": ("الدول الآسيوية غير العربية", "Non-Arab Asian countries", "asia", "#d9a92a"),
    "nafta": ("دول اتفاقية التجارة الحرة لشمال أمريكا", "North America Free Trade Agreement countries", "americas", "#3f7f5a"),
    "eu": ("دول الاتحاد الأوروبي", "European Union countries", "europe", "#b84a45"),
    "other": ("تكتلات ودول أخرى", "Other economic blocs and countries", None, "#7a6ab0"),
}

# commodity chapters: words in the Arabic name -> (short Arabic, short English); first match wins
COMMODITIES = [
    ("عربات سيارة", "المركبات وأجزاؤها", "Vehicles & parts"),
    ("وقود معدني", "الوقود والزيوت المعدنية", "Mineral fuels & oils"),
    ("لؤلؤ طبيعي", "الحلي والمجوهرات", "Pearls, stones & jewellery"),
    ("البسة وتوابع البسة", "الألبسة وتوابعها", "Apparel & clothing"),
    ("مفاعلات نووية", "الآلات والأجهزة الميكانيكية", "Machinery & mechanical appliances"),
    ("محضرات الصيدل", "محضرات الصيدلة", "Pharmaceutical products"),
    ("معدات كهربائية", "الآلات والأجهزة الكهربائية", "Electrical machinery & equipment"),
    ("اسمدة", "الأسمدة", "Fertilisers"),
    ("منتجات كيماوية غير عضوية", "كيماويات غير عضوية", "Inorganic chemicals"),
    ("منتجات كيماوية عضوية", "كيماويات عضوية", "Organic chemicals"),
    ("لدائن", "اللدائن ومصنوعاتها", "Plastics & articles thereof"),
    ("ملح, كبريت", "الفوسفات والمنتجات التعدينية", "Phosphates, salt & minerals"),
    ("حبوب", "الحبوب", "Cereals"),
    ("فواكه واثمار", "الفواكه والمكسرات", "Edible fruit & nuts"),
    ("اقمشة مصنرة", "الأقمشة المصنرة", "Knitted fabrics"),
    ("مواد أخرى", "مواد أخرى", "Other goods"),
    ("حديد صب", "الحديد والصلب", "Iron & steel"),
    ("حيوانات حية", "الحيوانات الحية", "Live animals"),
    ("صابون", "الصابون ومحضرات الغسيل", "Soap & washing preparations"),
    ("بن, شاي", "البن والشاي والبهارات", "Coffee, tea & spices"),
    ("لحوم واحشاء", "اللحوم", "Meat"),
    ("الومنيوم", "الألمنيوم ومصنوعاته", "Aluminium"),
    ("ورق وورق مقوى", "الورق والكرتون", "Paper & paperboard"),
    ("البان ومنتجات", "الألبان والبيض والعسل", "Dairy, eggs & honey"),
    ("محضرات غذائية منوعة", "محضرات غذائية منوعة", "Miscellaneous food preparations"),
    ("خضر وبعض", "الخضار", "Vegetables"),
    ("سكر ", "السكر ومصنوعاته", "Sugars"),
    ("دهون وزيوت", "الدهون والزيوت", "Fats & oils"),
    ("مصنوعات من حديد", "مصنوعات الحديد والصلب", "Articles of iron or steel"),
    ("نحاس", "النحاس ومصنوعاته", "Copper"),
    ("مطاط", "المطاط ومصنوعاته", "Rubber"),
    ("اثاث", "الأثاث", "Furniture"),
    ("زجاج", "الزجاج ومصنوعاته", "Glass"),
    ("اجهزة واداوات للبصريات", "أجهزة البصريات والطب", "Optical & medical instruments"),
    ("زيوت عطرية", "العطور ومستحضرات التجميل", "Essential oils & cosmetics"),
    ("تبغ", "التبغ", "Tobacco"),
]

LABELS = {
    "ar": {"national": "الصادرات الوطنية", "reexports": "إعادة التصدير", "total_exports": "إجمالي الصادرات",
           "imports": "المستوردات", "total": "إجمالي التجارة الخارجية", "balance": "الميزان التجاري",
           "unit": "مليون دينار", "trade": "التجارة الخارجية", "vs": "مقارنة مع", "change": "نسبة التغير"},
    "en": {"national": "National exports", "reexports": "Re-exports", "total_exports": "Total exports",
           "imports": "Imports", "total": "Total foreign trade", "balance": "Trade balance",
           "unit": "JD million", "trade": "Foreign\ntrade", "vs": "vs", "change": "change"},
}
FLOWS = {"Export": "national", "Re-Export": "reexports", "Import": "imports"}


# ============================================================== the data
class Trade:
    def __init__(self, path: Path, english: Path | None = None):
        self.path = Path(path)
        raw = pd.read_csv(path) if self.path.suffix.lower() == ".csv" else pd.read_excel(path)
        need = {"trade_type", "country", "commodity_name", "year", "value"}
        if not need <= set(raw.columns):
            raise SystemExit(f"The data needs the columns {sorted(need)}; it has {list(raw.columns)}")
        if "unit" in raw.columns:
            raw = raw[raw["unit"].astype(str).str.lower() == "value"]
        d = raw[list(need)].copy()
        d["value"] = pd.to_numeric(d["value"], errors="coerce").fillna(0) / MILLION
        d["flow"] = d["trade_type"].map(FLOWS)
        d = d[d["flow"].notna()]
        names = {c: (COUNTRY_FIX.get(c) or country_code(c)) for c in d["country"].unique()}
        d["iso"] = d["country"].map(names)
        d["bloc"] = d["iso"].map(self._bloc)
        en_names = self._english_commodities(raw, english)
        labels = {c: self._commodity(c, en_names.get(c)) for c in d["commodity_name"].unique()}
        d["goods_ar"] = d["commodity_name"].map(lambda c: labels[c][0])
        d["goods_en"] = d["commodity_name"].map(lambda c: labels[c][1])
        self.d = d
        self.years = sorted(int(y) for y in d["year"].unique())
        self.year, self.prev = self.years[-1], (self.years[-2] if len(self.years) > 1 else None)
        self.unknown = sorted(c for c, k in names.items() if not k)

    @staticmethod
    def _bloc(iso):
        if iso in GAFTA:
            return "gafta"
        if iso in ASIA:
            return "asia"
        if iso in NAFTA:
            return "nafta"
        if iso in EU:
            return "eu"
        return "other"

    @staticmethod
    def _english_commodities(raw_ar, english) -> dict:
        """Arabic chapter name -> English chapter name, matched on identical yearly totals."""
        if not english or not Path(english).exists():
            return {}
        en = pd.read_excel(english) if str(english).lower().endswith("xlsx") else pd.read_csv(english)

        def prints(df):
            g = df.groupby(["commodity_name", "trade_type", "year"])["value"].sum().round(0)
            return {name: tuple(sorted(s.items())) for name, s in g.groupby(level=0)}
        by_print = {}
        for name, fp in prints(en).items():
            by_print.setdefault(fp, name)
        return {name: by_print.get(fp) for name, fp in prints(raw_ar).items()}

    @staticmethod
    def _commodity(name: str, english: str | None):
        text = str(name)
        for key, ar, en in COMMODITIES:
            if key in text:
                return ar, en
        ar = re.split(r"[,،]", re.sub(r"^\S*\d\S*\s+", "", text))[0].strip()[:40]
        en = re.split(r"[;,]", english)[0].strip()[:40] if english else ar
        return ar, en

    # -------------------------------------------------------- numbers
    def rows(self, year=None, bloc=None, flow=None, goods=None):
        d = self.d
        if year is not None:
            d = d[d["year"] == year]
        if bloc:
            d = d[d["bloc"] == bloc]
        if flow:
            d = d[d["flow"] == flow]
        if goods:
            d = d[d["goods_ar"] == goods]
        return d

    def indicators(self, year, bloc=None) -> dict:
        f = self.rows(year, bloc).groupby("flow")["value"].sum()
        nat, rex, imp = (float(f.get(k, 0)) for k in ("national", "reexports", "imports"))
        return {"national": nat, "reexports": rex, "total_exports": nat + rex, "imports": imp,
                "total": nat + rex + imp, "balance": nat + rex - imp}

    def by_country(self, flow, year, bloc=None) -> pd.Series:
        s = self.rows(year, bloc, flow).groupby("iso")["value"].sum()
        return s[s > 0].sort_values(ascending=False)

    def by_goods(self, flow, year, lang) -> pd.Series:
        s = self.rows(year, flow=flow).groupby(f"goods_{lang}")["value"].sum()
        return s[s > 0].sort_values(ascending=False)


def cname(iso, lang) -> str:
    return SHORT[lang].get(iso) or country_name(iso, lang) or iso


def flag_names(isos) -> list:
    return [country_name(i, "en") or i for i in isos]


def pct(new, old):
    return round((new / old - 1) * 100, 1) if old else None


# ============================================================== the charts
SECTIONS = {   # id: (Arabic title, English title)
    "overview": ("مؤشرات التجارة الخارجية", "Foreign trade indicators"),
    "exports": ("وجهات الصادرات الوطنية", "Export destinations"),
    "imports": ("مصادر المستوردات", "Import sources"),
    "export_goods": ("السلع المصدرة", "Exported goods"),
    "import_goods": ("السلع المستوردة", "Imported goods"),
    "blocs": ("التجارة حسب التكتل الاقتصادي", "Trade by economic bloc"),
    "bloc_detail": ("التجارة مع كل تكتل", "Trade with each bloc"),
    "goods_focus": ("سلعة عبر ثلاث سنوات", "One commodity over the years"),
}
CHARTS = []   # (section, slug, Arabic caption, English caption, function(t, lang, style) -> chart)


def chart(section, slug, cap_ar, cap_en):
    def register(fn):
        CHARTS.append((section, slug, cap_ar, cap_en, fn))
        return fn
    return register


def T(lang, ar, en):
    return ar if lang == "ar" else en


# -------- 1. overview
@chart("overview", "1a_indicators_vs_last_year", "مقارنة المؤشرات بين سنتين (أعمدة مجمعة)", "Indicators, two years side by side")
def indicators_grouped(t, lang, style, bloc=None, title=None):
    L = LABELS[lang]
    keys = ["national", "reexports", "total_exports", "imports", "total", "balance"]
    now, before = t.indicators(t.year, bloc), t.indicators(t.prev, bloc)
    return cv.multibarplot([L[k] for k in keys], {str(t.prev): [before[k] for k in keys], str(t.year): [now[k] for k in keys]},
                           title=title or T(lang, f"مؤشرات التجارة الخارجية: {t.year} مقارنة مع {t.prev}",
                                            f"Foreign trade indicators: {t.year} vs {t.prev}"),
                           subtitle=L["unit"], **style)


@chart("overview", "1b_key_figures", "بطاقات الأرقام الرئيسية مع نسبة التغير", "Key figure cards with % change")
def key_figures(t, lang, style):
    L = LABELS[lang]
    now, before = t.indicators(t.year), t.indicators(t.prev)
    icons = {"national": "package-export", "reexports": "refresh", "imports": "package-import", "balance": "scale"}
    cards = [{"label": L[k], "value": now[k], "unit": L["unit"], "icon": icons[k],
              "change": None if k == "balance" else pct(now[k], before[k])} for k in icons]
    return cv.kpi_cards(cards, decimals=1, title=T(lang, f"التجارة الخارجية في لمحة {t.year}", f"Foreign trade at a glance, {t.year}"),
                        subtitle=T(lang, f"نسبة التغير مقارنة مع {t.prev}", f"change vs {t.prev}"), **style)


@chart("overview", "1c_three_years", "تطور التدفقات عبر السنوات (خطوط)", "Flows over the years (lines)")
def flows_over_time(t, lang, style):
    L = LABELS[lang]
    series = {L[k]: [t.indicators(y)[k] for y in t.years] for k in ("national", "reexports", "imports")}
    return cv.lineplot([str(y) for y in t.years], series,
                       title=T(lang, f"تطور التجارة الخارجية {t.years[0]}–{t.year}", f"Foreign trade, {t.years[0]}–{t.year}"),
                       subtitle=L["unit"], **style)


@chart("overview", "1d_change", "نسبة التغير لكل مؤشر", "% change of each indicator")
def indicators_change(t, lang, style):
    L = LABELS[lang]
    keys = ["national", "reexports", "total_exports", "imports", "total"]
    now, before = t.indicators(t.year), t.indicators(t.prev)
    return cv.barplot([L[k] for k in keys], [pct(now[k], before[k]) for k in keys], highlight="max", flags=False,
                      value_format="{:+.1f}%", title=T(lang, f"نسبة التغير في المؤشرات: {t.year} مقارنة مع {t.prev}",
                                                        f"Change in the indicators: {t.year} vs {t.prev}"),
                      subtitle="%", **style)


# -------- 2 / 3. partners
def _top_bar(t, lang, style, flow, title_ar, title_en, bloc=None, n=TOP):
    s = t.by_country(flow, t.year, bloc).head(n)
    return cv.barplot([cname(i, lang) for i in s.index], s.round(1).tolist(), flags=flag_names(s.index),
                      title=T(lang, title_ar, title_en), subtitle=LABELS[lang]["unit"], **style)


def _dumbbell(t, lang, style, flow, title_ar, title_en, bloc=None, n=10):
    now = t.by_country(flow, t.year, bloc).head(n)
    before = t.by_country(flow, t.prev, bloc).reindex(now.index).fillna(0)
    return cv.dotplot([cname(i, lang) for i in now.index], now.round(1).tolist(), compare=before.round(1).tolist(),
                      names=(str(t.prev), str(t.year)), flags=flag_names(now.index),
                      title=T(lang, title_ar, title_en), subtitle=LABELS[lang]["unit"], **style)


@chart("exports", "2a_top_destinations", "أهم الوجهات (أعمدة مع الأعلام)", "Top destinations (bars with flags)")
def top_destinations(t, lang, style):
    return _top_bar(t, lang, style, "national", f"أهم وجهات الصادرات الوطنية {t.year}", f"Top export destinations, {t.year}")


@chart("exports", "2b_destinations_vs_last_year", "مقارنة سنتين لكل دولة (دمبل)", "Two years per country (dumbbell)")
def destinations_compare(t, lang, style):
    return _dumbbell(t, lang, style, "national", f"وجهات الصادرات الوطنية: {t.year} مقارنة مع {t.prev}",
                     f"Export destinations: {t.year} vs {t.prev}")


@chart("exports", "2c_world_map", "خريطة العالم", "World map")
def destinations_map(t, lang, style):
    s = t.by_country("national", t.year)
    return cv.geoplot([cname(i, lang) for i in s.index], s.round(1).tolist(), region="world",
                      title=T(lang, f"الصادرات الوطنية حسب الدولة {t.year}", f"National exports by country, {t.year}"),
                      subtitle=LABELS[lang]["unit"], **style)


@chart("imports", "3a_top_sources", "أهم المصادر (أعمدة مع الأعلام)", "Top sources (bars with flags)")
def top_sources(t, lang, style):
    return _top_bar(t, lang, style, "imports", f"أهم مصادر المستوردات {t.year}", f"Top import sources, {t.year}")


@chart("imports", "3b_sources_vs_last_year", "مقارنة سنتين لكل دولة (دمبل)", "Two years per country (dumbbell)")
def sources_compare(t, lang, style):
    return _dumbbell(t, lang, style, "imports", f"مصادر المستوردات: {t.year} مقارنة مع {t.prev}",
                     f"Import sources: {t.year} vs {t.prev}")


@chart("imports", "3c_flow_map", "خريطة التدفقات إلى الأردن", "Flows into Jordan (map)")
def sources_flowmap(t, lang, style):
    s = t.by_country("imports", t.year).head(12)
    return cv.flowmap([cname(i, lang) for i in s.index], s.round(1).tolist(), hub="Jordan", direction="in",
                      title=T(lang, f"تدفقات المستوردات إلى الأردن {t.year}", f"Imports flowing into Jordan, {t.year}"),
                      subtitle=LABELS[lang]["unit"], **style)


# -------- 4 / 5. goods
def _goods_bar(t, lang, style, flow, title_ar, title_en):
    s = t.by_goods(flow, t.year, lang).head(TOP)
    return cv.barplot(s.index.tolist(), s.round(1).tolist(), flags=False, label_wrap=16,
                      title=T(lang, title_ar, title_en), subtitle=LABELS[lang]["unit"], **style)


def _goods_treemap(t, lang, style, flow, title_ar, title_en):
    s = t.by_goods(flow, t.year, lang).head(12)
    return cv.treemap(s.index.tolist(), s.round(1).tolist(), flags=False,
                      title=T(lang, title_ar, title_en), subtitle=LABELS[lang]["unit"], **style)


def _goods_trend(t, lang, style, flow, title_ar, title_en):
    top = t.by_goods(flow, t.year, lang).head(5).index
    col = f"goods_{lang}"
    g = t.rows(flow=flow).groupby([col, "year"])["value"].sum()
    series = {name: [float(g.get((name, y), 0)) for y in t.years] for name in top}
    return cv.lineplot([str(y) for y in t.years], series, value_labels=False,
                       title=T(lang, title_ar, title_en), subtitle=LABELS[lang]["unit"], **style)


@chart("export_goods", "4a_top_goods", "أهم السلع (أعمدة)", "Top goods (bars)")
def top_export_goods(t, lang, style):
    return _goods_bar(t, lang, style, "national", f"أهم السلع المصدرة {t.year}", f"Top exported goods, {t.year}")


@chart("export_goods", "4b_structure", "هيكل الصادرات (مربعات)", "Structure (treemap)")
def export_goods_treemap(t, lang, style):
    return _goods_treemap(t, lang, style, "national", f"هيكل الصادرات الوطنية {t.year}", f"What Jordan exports, {t.year}")


@chart("export_goods", "4c_trend", "أهم 5 سلع عبر السنوات", "Top 5 goods over the years")
def export_goods_trend(t, lang, style):
    return _goods_trend(t, lang, style, "national", f"أهم السلع المصدرة {t.years[0]}–{t.year}",
                        f"Top exported goods, {t.years[0]}–{t.year}")


@chart("import_goods", "5a_top_goods", "أهم السلع (أعمدة)", "Top goods (bars)")
def top_import_goods(t, lang, style):
    return _goods_bar(t, lang, style, "imports", f"أهم السلع المستوردة {t.year}", f"Top imported goods, {t.year}")


@chart("import_goods", "5b_structure", "هيكل المستوردات (مربعات)", "Structure (treemap)")
def import_goods_treemap(t, lang, style):
    return _goods_treemap(t, lang, style, "imports", f"هيكل المستوردات {t.year}", f"What Jordan imports, {t.year}")


@chart("import_goods", "5c_trend", "أهم 5 سلع عبر السنوات", "Top 5 goods over the years")
def import_goods_trend(t, lang, style):
    return _goods_trend(t, lang, style, "imports", f"أهم السلع المستوردة {t.years[0]}–{t.year}",
                        f"Top imported goods, {t.years[0]}–{t.year}")


# -------- 6. blocs
def _bloc_name(key, lang):
    return BLOCS[key][0] if lang == "ar" else BLOCS[key][1]


@chart("blocs", "6a_share_donut", "حصة كل تكتل (دونات)", "Share of each bloc (donut)")
def blocs_donut(t, lang, style):
    keys = ["gafta", "asia", "nafta", "eu", "other"]
    vals = [t.indicators(t.year, k)["total"] for k in keys]
    colors = [BLOCS[k][3] for k in keys] if style.get("design") == "report_slate" else None
    return cv.pieplot([_bloc_name(k, lang) for k in keys], vals, colors=colors, sort=None, show_values=False,
                      flags=False, center_text=LABELS[lang]["trade"].replace("\n", " ") if lang == "ar" else "Foreign trade",
                      center_label="", title=T(lang, f"التجارة الخارجية حسب التكتل الاقتصادي {t.year}",
                                               f"Foreign trade by country group, {t.year}"), **style)


@chart("blocs", "6b_flows_by_bloc", "الصادرات والمستوردات لكل تكتل", "Exports and imports per bloc")
def blocs_flows(t, lang, style):
    L = LABELS[lang]
    keys = ["gafta", "asia", "nafta", "eu", "other"]
    ind = {k: t.indicators(t.year, k) for k in keys}
    short = {"gafta": T(lang, "العربية الكبرى", "Arab FTA"), "asia": T(lang, "آسيا غير العربية", "Non-Arab Asia"),
             "nafta": T(lang, "شمال أمريكا", "North America"), "eu": T(lang, "الاتحاد الأوروبي", "EU"),
             "other": T(lang, "أخرى", "Other")}
    return cv.multibarplot([short[k] for k in keys], {L[f]: [ind[k][f] for k in keys] for f in ("national", "reexports", "imports")},
                           title=T(lang, f"التجارة مع التكتلات الاقتصادية {t.year}", f"Trade with each country group, {t.year}"),
                           subtitle=L["unit"], **style)


@chart("blocs", "6c_balance_by_bloc", "الميزان التجاري مع كل تكتل", "Trade balance with each bloc")
def blocs_balance(t, lang, style):
    keys = ["gafta", "asia", "nafta", "eu", "other"]
    short = {"gafta": T(lang, "العربية الكبرى", "Arab FTA"), "asia": T(lang, "آسيا غير العربية", "Non-Arab Asia"),
             "nafta": T(lang, "شمال أمريكا", "North America"), "eu": T(lang, "الاتحاد الأوروبي", "EU"),
             "other": T(lang, "أخرى", "Other")}
    return cv.barplot([short[k] for k in keys], [round(t.indicators(t.year, k)["balance"], 1) for k in keys],
                      highlight=None, flags=False,
                      title=T(lang, f"الميزان التجاري مع التكتلات الاقتصادية {t.year}", f"Trade balance by country group, {t.year}"),
                      subtitle=T(lang, "موجب = فائض، سالب = عجز · مليون دينار", "positive = surplus, negative = deficit · JD million"),
                      **style)


# -------- 7. one chart set per bloc (the tables 7, 9, 11, 13)
def _bloc_charts(key):
    ar, en, region, _ = BLOCS[key]

    def indicators(t, lang, style):
        return indicators_grouped(t, lang, style, bloc=key, title=T(lang, f"التجارة مع {ar}: {t.year} مقارنة مع {t.prev}",
                                                                    f"Trade with {en}: {t.year} vs {t.prev}"))

    def exports(t, lang, style):
        return _dumbbell(t, lang, style, "national", f"وجهات الصادرات الوطنية في {ar}: {t.year} مقارنة مع {t.prev}",
                         f"Export destinations in {en}: {t.year} vs {t.prev}", bloc=key, n=5)

    def imports(t, lang, style):
        return _dumbbell(t, lang, style, "imports", f"مصادر المستوردات في {ar}: {t.year} مقارنة مع {t.prev}",
                         f"Import sources in {en}: {t.year} vs {t.prev}", bloc=key, n=5)

    def map_(t, lang, style):
        s = t.rows(t.year, key).groupby("iso")["value"].sum()
        s = s[s > 0]
        return cv.geoplot([cname(i, lang) for i in s.index], s.round(1).tolist(), region=region,
                          title=T(lang, f"التجارة مع {ar} حسب الدولة {t.year}", f"Trade with {en} by country, {t.year}"),
                          subtitle=LABELS[lang]["unit"], **style)

    CHARTS.append(("bloc_detail", f"7{key}_a_indicators", f"{ar}: المؤشرات", f"{en}: indicators", indicators))
    CHARTS.append(("bloc_detail", f"7{key}_b_exports", f"{ar}: أهم وجهات الصادرات", f"{en}: top destinations", exports))
    CHARTS.append(("bloc_detail", f"7{key}_c_imports", f"{ar}: أهم مصادر المستوردات", f"{en}: top sources", imports))
    CHARTS.append(("bloc_detail", f"7{key}_d_map", f"{ar}: الخريطة", f"{en}: map", map_))


for _key in ("gafta", "asia", "nafta", "eu"):
    _bloc_charts(_key)


# -------- 8. one commodity over the years
def _focus_charts(goods_ar, i):
    def flows(t, lang, style):
        L = LABELS[lang]
        name = goods_ar if lang == "ar" else t.rows(goods=goods_ar)["goods_en"].iloc[0]
        g = t.rows(goods=goods_ar).groupby(["flow", "year"])["value"].sum()
        series = {str(y): [float(g.get((f, y), 0)) for f in ("national", "reexports", "imports")] for y in t.years}
        return cv.multibarplot([L["national"], L["reexports"], L["imports"]], series,
                               title=T(lang, f"{name}: {t.years[0]}–{t.year}", f"{name}: {t.years[0]}–{t.year}"),
                               subtitle=L["unit"], **style)

    def partners(t, lang, style):
        rows = t.rows(t.year, goods=goods_ar)
        flow = rows.groupby("flow")["value"].sum().idxmax()      # the bigger side: imports or exports
        name = goods_ar if lang == "ar" else rows["goods_en"].iloc[0]
        s = rows[rows["flow"] == flow].groupby("iso")["value"].sum().sort_values(ascending=False).head(TOP)
        what = {"national": T(lang, "وجهات", "destinations"), "imports": T(lang, "مصادر", "sources"),
                "reexports": T(lang, "وجهات إعادة التصدير", "re-export destinations")}[flow]
        return cv.barplot([cname(c, lang) for c in s.index], s.round(1).tolist(), flags=flag_names(s.index),
                          title=T(lang, f"أهم {what} {name} {t.year}", f"{name}: top {what}, {t.year}"),
                          subtitle=LABELS[lang]["unit"], **style)

    CHARTS.append(("goods_focus", f"8{i}_a_flows", f"{goods_ar}: التدفقات حسب السنة", f"{goods_ar}: flows per year", flows))
    CHARTS.append(("goods_focus", f"8{i}_b_partners", f"{goods_ar}: أهم الشركاء", f"{goods_ar}: top partners", partners))


for _i, _g in enumerate(FOCUS, 1):
    _focus_charts(_g, _i)


# ============================================================== run + gallery
def gallery(out: Path, t: Trade, langs, designs, done):
    cards = {}
    for section, slug, cap_ar, cap_en, _ in CHARTS:
        if any((lang, design, slug) in done for lang in langs for design in designs):
            cards.setdefault(section, []).append((slug, cap_ar, cap_en))
    html = ["<!doctype html><html><head><meta charset='utf-8'><title>ACC trade charts</title><style>",
            "body{font-family:'Segoe UI',Tahoma,sans-serif;margin:0;background:#f5f6f8;color:#1f2937}",
            "header{position:sticky;top:0;background:#1f3a5f;color:#fff;padding:12px 24px;display:flex;gap:16px;align-items:center;flex-wrap:wrap;z-index:2}",
            "header h1{font-size:18px;margin:0 16px 0 0}button{border:1px solid #d9a92a;background:transparent;color:#fff;padding:6px 12px;border-radius:6px;cursor:pointer}",
            "button.on{background:#d9a92a;color:#1f3a5f}section{padding:8px 24px}h2{color:#1f3a5f;border-bottom:3px solid #d9a92a;display:inline-block}",
            ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(520px,1fr));gap:16px}",
            ".card{background:#fff;border-radius:10px;box-shadow:0 1px 4px rgba(0,0,0,.08);padding:10px}",
            ".card img{width:100%;border-radius:6px}.cap{font-size:14px;margin:6px 2px}.opt{color:#b8862e;font-weight:600}",
            "</style></head><body><header><h1>ACC trade charts · "
            f"{t.year} vs {t.prev}</h1>"]
    for lang in langs:
        html.append(f"<button data-lang='{lang}'>{'العربية' if lang == 'ar' else 'English'}</button>")
    html.append("<span style='width:24px'></span>")
    for design in designs:
        html.append(f"<button data-design='{design}'>{design}</button>")
    html.append("</header>")
    for section, items in cards.items():
        ar, en = SECTIONS[section]
        html.append(f"<section><h2 data-ar='{ar}' data-en='{en}'>{ar}</h2><div class='grid'>")
        for k, (slug, cap_ar, cap_en) in enumerate(items):
            html.append(f"<div class='card'><img data-slug='{slug}' loading='lazy'>"
                        f"<div class='cap'><span class='opt'>{chr(65 + k % 26)}</span> · "
                        f"<span data-ar='{cap_ar}' data-en='{cap_en}'>{cap_ar}</span></div></div>")
        html.append("</div></section>")
    html.append(f"""<script>
let lang='{langs[0]}', design='{designs[0]}';
function show(){{
  document.querySelectorAll('img[data-slug]').forEach(i=>i.src=lang+'/'+design+'/'+i.dataset.slug+'.png');
  document.querySelectorAll('[data-ar]').forEach(e=>e.textContent=lang=='ar'?e.dataset.ar:e.dataset.en);
  document.body.dir=lang=='ar'?'rtl':'ltr';
  document.querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.dataset.lang==lang||b.dataset.design==design));
}}
document.querySelectorAll('button').forEach(b=>b.onclick=()=>{{if(b.dataset.lang)lang=b.dataset.lang;if(b.dataset.design)design=b.dataset.design;show();}});
show();
</script></body></html>""")
    (out / "index.html").write_text("\n".join(html), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description="ACC trade charts in four designs, Arabic and English.")
    ap.add_argument("data", nargs="?", default=str(DATA), help="the cleaned trade data (xlsx or csv)")
    ap.add_argument("--english", default=str(DATA_EN), help="the English file (for commodity names)")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--lang", nargs="*", default=LANGS, choices=LANGS)
    ap.add_argument("--designs", nargs="*", default=DESIGNS, choices=cv.list_designs())
    ap.add_argument("--only", nargs="*", help=f"sections: {', '.join(SECTIONS)}")
    args = ap.parse_args(argv)

    t = Trade(Path(args.data), Path(args.english))
    out = Path(args.out)
    todo = [c for c in CHARTS if not args.only or c[0] in args.only]
    print(f"{t.path.name}: {t.years[0]}–{t.year}, report year {t.year} vs {t.prev} · {len(todo)} charts × "
          f"{len(args.designs)} designs × {len(args.lang)} languages")
    if t.unknown:
        print("  countries without a map position:", ", ".join(t.unknown))
    done, failed, started = set(), [], time.perf_counter()
    for lang in args.lang:
        for design in args.designs:
            folder = out / lang / design
            folder.mkdir(parents=True, exist_ok=True)
            style = dict(design=design, figure_size=SIZE, logo=None)
            with PdfPages(folder / f"acc_trade_charts_{lang}_{design}.pdf") as pdf:
                for section, slug, *_, fn in todo:
                    try:
                        c = fn(t, lang, style)
                        c.save(str(folder / f"{slug}.png"), dpi=DPI)
                        pdf.savefig(c.fig)
                        c.close()
                        done.add((lang, design, slug))
                    except Exception as exc:
                        failed.append(f"{lang}/{design}/{slug}: {type(exc).__name__}: {exc}")
            print(f"  {lang} · {design}: {sum(1 for d in done if d[:2] == (lang, design))} charts")
    gallery(out, t, args.lang, args.designs, done)
    print(f"{len(done)} images in {time.perf_counter() - started:.0f}s · open {out / 'index.html'}")
    for f in failed:
        print("  ✗", f)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
