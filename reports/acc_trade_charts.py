"""ACC trade charts: a fixed set of charts from the cleaned foreign-trade dataset
(arabic_cleaned_trade_data_ar_full_2023_2025.xlsx or a CSV with the same columns), drawn in four
designs and in Arabic and English. Each section offers two to six chart ideas to choose from.

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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))      # run with any Python, also when chamberviz is not installed

import chamberviz as cv  # noqa: E402
from chamberviz.assets_lookup import country_code, country_info, country_name  # noqa: E402

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
LOGO = HERE / "assets" / "acc_logo_white.png"   # Amman Chamber of Commerce; None = no logo
LOGO_CORNER = "top-right"                 # top-left, top-right, bottom-left or bottom-right
LOGO_SIZE = 0.12                          # logo height as a share of the chart height

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
SOUTH_AMERICA = set("BR AR CL CO PE VE EC BO PY UY GY SR".split())
_REG = json.loads((ROOT / "chamberstudio" / "regions.json").read_text(encoding="utf-8"))["regions"]
EU = set(_REG["EU"]["countries"])
ASIA = set(_REG["Asia"]["countries"])      # non-Arab Asia, incl. Turkey and Israel (as in the tables)
# which countries each regional map shows (the map rectangle alone would put Saudi Arabia on the
# Africa map or Israel on the Gulf map); other regions fall back to the countries inside the rectangle
ARAB_ASIA = set("SA AE KW QA BH OM YE IQ SY LB PS JO".split())
ARAB_AFRICA = set("EG LY TN DZ MA SD MR SO DJ KM".split())
OTHER_EUROPE = set("GB CH NO IS UA BY RS BA AL MK ME MD XK RU LI MC AD SM".split())
MAP_COUNTRIES = {"asia": ASIA | ARAB_ASIA, "europe": EU | OTHER_EUROPE, "gcc": set(_REG["GCC"]["countries"]),
                 "africa": set(_REG["Africa"]["countries"]) | ARAB_AFRICA}
BLOCS = {   # key: (Arabic, English, map region, colour in the bloc donut)
    "gafta": ("منطقة التجارة الحرة العربية الكبرى", "Greater Arab Free Trade Area", "arab_world", "#1f3a5f"),
    "asia": ("الدول الآسيوية غير العربية", "Non-Arab Asian countries", "asia", "#d9a92a"),
    "nafta": ("دول اتفاقية التجارة الحرة لشمال أمريكا", "North America Free Trade Agreement countries", "north_america", "#3f7f5a"),
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
    ("حبوب واثمار زيتية", "البذور والثمار الزيتية", "Oil seeds"),
    ("محضرات اساسها", "محضرات الحبوب والمخبوزات", "Cereal & bakery preparations"),
    ("منتجات مطاحن", "منتجات المطاحن", "Milling products"),
    ("حبوب", "الحبوب", "Cereals"),
    ("فواكه واثمار", "الفواكه والمكسرات", "Edible fruit & nuts"),
    ("اقمشة مصنرة", "الأقمشة المصنرة", "Knitted fabrics"),
    ("مواد أخرى", "مواد أخرى", "Other goods"),
    ("مصنوعات من حديد", "مصنوعات الحديد والصلب", "Articles of iron or steel"),
    ("حديد صب", "الحديد والصلب", "Iron & steel"),
    ("حيوانات حية", "الحيوانات الحية", "Live animals"),
    ("صابون", "الصابون ومحضرات الغسيل", "Soap & washing preparations"),
    ("بن, شاي", "البن والشاي والبهارات", "Coffee, tea & spices"),
    ("لحوم واحشاء", "اللحوم", "Meat"),
    ("الومنيوم", "الألمنيوم ومصنوعاته", "Aluminium"),
    ("ورق وورق مقوى", "الورق والكرتون", "Paper & paperboard"),
    ("البان ومنتجات", "الألبان والبيض والعسل", "Dairy, eggs & honey"),
    ("محضرات غذائية منوعة", "محضرات غذائية منوعة", "Miscellaneous food preparations"),
    ("سكر ", "السكر ومصنوعاته", "Sugars"),
    ("دهون وزيوت", "الدهون والزيوت", "Fats & oils"),
    ("نحاس", "النحاس ومصنوعاته", "Copper"),
    ("مطاط", "المطاط ومصنوعاته", "Rubber"),
    ("اثاث", "الأثاث", "Furniture"),
    ("زجاج", "الزجاج ومصنوعاته", "Glass"),
    ("للبصريات", "أجهزة البصريات والطب", "Optical & medical instruments"),
    ("زيوت عطرية", "العطور ومستحضرات التجميل", "Essential oils & cosmetics"),
    ("تبغ", "التبغ", "Tobacco"),
    ("خضر ونباتات", "الخضار", "Vegetables"),
    ("منتجات كيماوية منوعة", "منتجات كيماوية منوعة", "Miscellaneous chemical products"),
    ("محضرات خضر", "محضرات الخضار والفواكه", "Prepared vegetables & fruit"),
    ("بقايا ونفايات صناعات الاغذية", "أعلاف الحيوانات", "Animal feed & food residues"),
    ("طائرات", "الطائرات وأجزاؤها", "Aircraft & parts"),
    ("مشروبات", "المشروبات", "Beverages"),
    ("خشب ومصنوعاته", "الخشب ومصنوعاته", "Wood & articles of wood"),
    ("شعيرات تركيبية", "الشعيرات التركيبية", "Man-made filaments"),
    ("خلاصات للدباغة", "الدهانات والأصباغ والأحبار", "Paints, dyes & inks"),
    ("كاكاو", "الكاكاو ومحضراته", "Cocoa"),
    ("مصنوعات متنوعة", "مصنوعات متنوعة", "Miscellaneous manufactures"),
    ("منتجات خزف", "منتجات الخزف", "Ceramic products"),
    ("محضرات لحوم", "محضرات اللحوم والأسماك", "Prepared meat & fish"),
    ("احذية", "الأحذية", "Footwear"),
    ("اصناف اخر جاهزة من مواد نسجية", "المنسوجات الجاهزة الأخرى", "Other made-up textiles"),
    ("عجينة الخشب", "عجينة الورق ونفاياته", "Wood pulp & waste paper"),
    ("اصناف منوعة من معادن عادية", "مصنوعات معدنية منوعة", "Misc. articles of base metal"),
    ("مصنوعات من حجر", "مصنوعات الحجر والإسمنت", "Articles of stone & cement"),
    ("اسماك وقشريات", "الأسماك", "Fish & seafood"),
    ("سجاد", "السجاد", "Carpets"),
    ("الياف تركيبية", "الألياف التركيبية", "Man-made staple fibres"),
    ("حشو,لباد", "اللباد والحبال", "Wadding, felt & ropes"),
    ("لعب اطفال", "الألعاب ولوازم الرياضة", "Toys, games & sports goods"),
    ("نسج خاصة", "الأقمشة الخاصة", "Special woven fabrics"),
    ("كتب, صحف", "الكتب والمطبوعات", "Books & printed matter"),
    ("الساعات", "الساعات", "Clocks & watches"),
    ("مواد زلالية", "الغراء والإنزيمات", "Glues, starches & enzymes"),
    ("عدد وادوات", "العدد والأدوات المعدنية", "Tools & cutlery"),
    ("مصنوعات من الجلد", "المصنوعات الجلدية", "Leather goods & bags"),
    ("قطن", "القطن", "Cotton"),
    ("نسج مشربة", "الأقمشة المطلية", "Coated textile fabrics"),
    ("اشجار ونباتات", "النباتات والأزهار", "Plants & flowers"),
    ("رصاص", "الرصاص", "Lead"),
    ("صوف", "الصوف", "Wool"),
    ("قطارات", "معدات السكك الحديدية", "Railway equipment"),
    ("سفن وقوارب", "السفن والقوارب", "Ships & boats"),
    ("الياف نسجية نباتية", "الألياف النباتية الأخرى", "Other vegetable fibres"),
    ("صمغ اللك", "الصموغ والراتنجات", "Gums & resins"),
    ("منتجات تصوير", "منتجات التصوير", "Photographic goods"),
    ("زنك", "الزنك", "Zinc"),
    ("خامات معادن", "خامات المعادن", "Ores, slag & ash"),
    ("بارود ومتفجرات", "المتفجرات والثقاب", "Explosives & matches"),
    ("مواد ضفر نباتية", "مواد نباتية أخرى", "Other vegetable products"),
    ("جلود خام", "الجلود الخام والمدبوغة", "Raw hides & leather"),
    ("ريش وزغب", "الريش والأزهار الاصطناعية", "Feathers & artificial flowers"),
    ("اغطية راس", "أغطية الرأس", "Headgear"),
    ("نيكل", "النيكل", "Nickel"),
    ("جلود بفراء", "الفراء", "Furskins"),
    ("مصنوعات من القش", "مصنوعات القش", "Straw & basketware"),
    ("منتجات اخر من اصل حيواني", "منتجات حيوانية أخرى", "Other animal products"),
    ("مظلات", "المظلات", "Umbrellas"),
    ("تحف فنية", "التحف الفنية", "Works of art & antiques"),
    ("قصدير", "القصدير", "Tin"),
    ("ادوات موسيقية", "الآلات الموسيقية", "Musical instruments"),
    ("معادن عادية اخر", "معادن عادية أخرى", "Other base metals"),
    ("فلين", "الفلين", "Cork"),
    ("حرير طبيعي", "الحرير", "Silk"),
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
    def rows(self, year=None, bloc=None, flow=None, goods=None, isos=None):
        d = self.d
        if year is not None:
            d = d[d["year"] == year]
        if bloc:
            d = d[d["bloc"] == bloc]
        if flow:
            d = d[d["flow"] == flow]
        if goods:
            d = d[d["goods_ar"] == goods]
        if isos is not None:
            d = d[d["iso"].isin(isos)]
        return d

    def indicators(self, year, bloc=None, isos=None) -> dict:
        f = self.rows(year, bloc, isos=isos).groupby("flow")["value"].sum()
        nat, rex, imp = (float(f.get(k, 0)) for k in ("national", "reexports", "imports"))
        return {"national": nat, "reexports": rex, "total_exports": nat + rex, "imports": imp,
                "total": nat + rex + imp, "balance": nat + rex - imp}

    def by_country(self, flow, year, bloc=None, isos=None) -> pd.Series:
        """Value per country; flow None = total trade (exports + re-exports + imports)."""
        s = self.rows(year, bloc, flow, isos=isos).groupby("iso")["value"].sum()
        return s[s > 0].sort_values(ascending=False)

    def balance_by_country(self, year) -> pd.Series:
        d = self.rows(year)
        out = d[d["flow"] != "imports"].groupby("iso")["value"].sum()
        return out.sub(d[d["flow"] == "imports"].groupby("iso")["value"].sum(), fill_value=0).sort_values()

    def by_goods(self, flow, year, lang) -> pd.Series:
        s = self.rows(year, flow=flow).groupby(f"goods_{lang}")["value"].sum()
        return s[s > 0].sort_values(ascending=False)


def logo_for(design: str, out: Path):
    """The logo for a design, trimmed of empty margins (white or transparent): as it is on light
    backgrounds; on a white rounded card on dark ones, where the navy lettering would disappear."""
    if not LOGO or not Path(LOGO).exists():
        return None
    r, g, b = (int(cv.get_design(design).surface.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    dark = 0.299 * r + 0.587 * g + 0.114 * b < 150
    path = out / "_logo" / ("acc_logo_card.png" if dark else "acc_logo.png")
    if not path.exists() or path.stat().st_mtime < Path(LOGO).stat().st_mtime:
        import numpy as np
        from PIL import Image, ImageDraw
        im = Image.open(LOGO).convert("RGBA")
        px = np.asarray(im)
        ink = (px[..., 3] > 20) & (px[..., :3].min(axis=2) < 235)   # neither transparent nor white
        rows, cols = np.where(ink)
        im = im.crop((cols.min(), rows.min(), cols.max() + 1, rows.max() + 1))
        if dark:
            pad = int(im.height * 0.12)
            bg = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
            ImageDraw.Draw(bg).rounded_rectangle([0, 0, bg.width - 1, bg.height - 1], radius=pad, fill="white")
            bg.alpha_composite(im, (pad, pad))
            im = bg
        path.parent.mkdir(parents=True, exist_ok=True)
        im.save(path)
    return str(path)


def cname(iso, lang) -> str:
    return SHORT[lang].get(iso) or country_name(iso, lang) or iso


def flag_names(isos) -> list:
    return [country_name(i, "en") or i for i in isos]


def pct(new, old):
    return round((new / old - 1) * 100, 1) if old else None


def gains(values) -> list:
    """Bars to highlight in a chart of changes or balances: the positive ones (gains, surplus)."""
    return [i for i, v in enumerate(values) if v > 0]


def in_region(s: pd.Series, region) -> pd.Series:
    """Only the countries of a map region, so a regional map is coloured by its own values
    (otherwise the USA or China would make every country on a Middle East map look pale)."""
    if region in MAP_COUNTRIES:
        return s[s.index.isin(MAP_COUNTRIES[region])]
    x0, x1, y0, y1 = cv.REGIONS[region]
    keep = [i for i in s.index if (c := country_info(i)) and c["lon"] is not None
            and x0 <= c["lon"] <= x1 and y0 <= c["lat"] <= y1]
    return s.loc[keep]


# ============================================================== the charts
SECTIONS = {   # id: (Arabic title, English title); the gallery and the PDFs follow this order
    "overview": ("مؤشرات التجارة الخارجية", "Foreign trade indicators"),
    "exports": ("وجهات الصادرات الوطنية", "Export destinations"),
    "imports": ("مصادر المستوردات", "Import sources"),
    "reexports": ("إعادة التصدير", "Re-exports"),
    "partners": ("الشركاء التجاريون والميزان التجاري", "Trading partners and the trade balance"),
    "export_goods": ("السلع المصدرة", "Exported goods"),
    "import_goods": ("السلع المستوردة", "Imported goods"),
    "blocs": ("التجارة حسب التكتل الاقتصادي", "Trade by economic bloc"),
    "bloc_detail": ("التجارة مع كل تكتل", "Trade with each bloc"),
    "americas": ("أمريكا الشمالية وأمريكا الجنوبية", "North America and South America"),
    "regions": ("خرائط المناطق", "Regional maps"),
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


@chart("overview", "1e_balance_trend", "الميزان التجاري عبر السنوات", "Trade balance over the years")
def balance_trend(t, lang, style):
    return cv.barplot([str(y) for y in t.years], [round(t.indicators(y)["balance"], 1) for y in t.years],
                      highlight=None, flags=False,
                      title=T(lang, f"الميزان التجاري {t.years[0]}–{t.year}", f"Trade balance, {t.years[0]}–{t.year}"),
                      subtitle=T(lang, "سالب = عجز · مليون دينار", "negative = deficit · JD million"), **style)


@chart("overview", "1f_coverage", "نسبة تغطية الصادرات للمستوردات", "Export coverage of imports")
def coverage(t, lang, style):
    vals = [round(t.indicators(y)["total_exports"] / t.indicators(y)["imports"] * 100, 1) for y in t.years]
    return cv.barplot([str(y) for y in t.years], vals, highlight="last", flags=False, value_format="{:.1f}%",
                      title=T(lang, f"نسبة تغطية الصادرات الكلية للمستوردات {t.years[0]}–{t.year}",
                              f"Total exports as a share of imports, {t.years[0]}–{t.year}"),
                      subtitle=T(lang, "إجمالي الصادرات ÷ المستوردات", "total exports ÷ imports"), **style)


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


def _changes(t, lang, style, flow, title_ar, title_en, n=5):
    """The countries that grew most and fell most (JD million), biggest gain on top."""
    now, before = t.by_country(flow, t.year), t.by_country(flow, t.prev)
    diff = now.sub(before, fill_value=0).sort_values(ascending=False)
    s = pd.concat([diff.head(n), diff.tail(n)]) if len(diff) > 2 * n else diff
    s = s[~s.index.duplicated()]
    return cv.barplot([cname(i, lang) for i in s.index], s.round(1).tolist(), horizontal=True, sort=None,
                      highlight=gains(s), flags=flag_names(s.index), value_format="{:+,.1f}",
                      title=T(lang, title_ar, title_en),
                      subtitle=T(lang, f"التغير بالمليون دينار، {t.year} مقارنة مع {t.prev}",
                                 f"change in JD million, {t.year} vs {t.prev}"), **style)


def _region_map(t, lang, style, flow, region, title_ar, title_en):
    s = in_region(t.by_country(flow, t.year), region)
    return cv.geoplot([cname(i, lang) for i in s.index], s.round(1).tolist(), region=region,
                      title=T(lang, title_ar, title_en), subtitle=LABELS[lang]["unit"], **style)


@chart("exports", "2d_middle_east_map", "خريطة الشرق الأوسط", "Middle East map")
def destinations_middle_east(t, lang, style):
    return _region_map(t, lang, style, "national", "middle_east", f"الصادرات الوطنية إلى دول الشرق الأوسط {t.year}",
                       f"National exports to the Middle East, {t.year}")


@chart("exports", "2e_biggest_changes", "أكبر زيادة وأكبر تراجع", "Biggest gains and falls")
def destinations_changes(t, lang, style):
    return _changes(t, lang, style, "national", "أكبر تغير في الصادرات الوطنية حسب الوجهة",
                    "Export destinations: biggest gains and falls")


@chart("exports", "2f_flows_out", "خريطة التدفقات من الأردن", "Flows out of Jordan (map)")
def destinations_flowmap(t, lang, style):
    s = t.by_country("national", t.year).head(12)
    return cv.flowmap([cname(i, lang) for i in s.index], s.round(1).tolist(), hub="Jordan", direction="out",
                      title=T(lang, f"تدفقات الصادرات الوطنية من الأردن {t.year}", f"National exports flowing out of Jordan, {t.year}"),
                      subtitle=LABELS[lang]["unit"], **style)


@chart("imports", "3d_asia_map", "خريطة آسيا", "Asia map")
def sources_asia(t, lang, style):
    return _region_map(t, lang, style, "imports", "asia", f"المستوردات من دول آسيا {t.year}", f"Imports from Asia, {t.year}")


@chart("imports", "3e_europe_map", "خريطة أوروبا", "Europe map")
def sources_europe(t, lang, style):
    return _region_map(t, lang, style, "imports", "europe", f"المستوردات من دول أوروبا {t.year}", f"Imports from Europe, {t.year}")


@chart("imports", "3f_biggest_changes", "أكبر زيادة وأكبر تراجع", "Biggest gains and falls")
def sources_changes(t, lang, style):
    return _changes(t, lang, style, "imports", "أكبر تغير في المستوردات حسب المصدر", "Import sources: biggest gains and falls")


# -------- re-exports
@chart("reexports", "re_a_top_destinations", "أهم الوجهات (أعمدة مع الأعلام)", "Top destinations (bars with flags)")
def reexport_top(t, lang, style):
    return _top_bar(t, lang, style, "reexports", f"أهم وجهات إعادة التصدير {t.year}", f"Top re-export destinations, {t.year}")


@chart("reexports", "re_b_middle_east_map", "خريطة الشرق الأوسط", "Middle East map")
def reexport_map(t, lang, style):
    return _region_map(t, lang, style, "reexports", "middle_east", f"إعادة التصدير إلى دول الشرق الأوسط {t.year}",
                       f"Re-exports to the Middle East, {t.year}")


@chart("reexports", "re_c_trend", "أهم 5 وجهات عبر السنوات", "Top 5 destinations over the years")
def reexport_trend(t, lang, style):
    top = t.by_country("reexports", t.year).head(5).index
    g = t.rows(flow="reexports").groupby(["iso", "year"])["value"].sum()
    series = {cname(i, lang): [float(g.get((i, y), 0)) for y in t.years] for i in top}
    return cv.lineplot([str(y) for y in t.years], series, value_labels=False,
                       title=T(lang, f"أهم وجهات إعادة التصدير {t.years[0]}–{t.year}", f"Top re-export destinations, {t.years[0]}–{t.year}"),
                       subtitle=LABELS[lang]["unit"], **style)


@chart("reexports", "re_d_top_goods", "أهم السلع المعاد تصديرها", "Top re-exported goods")
def reexport_goods(t, lang, style):
    return _goods_bar(t, lang, style, "reexports", f"أهم السلع المعاد تصديرها {t.year}", f"Top re-exported goods, {t.year}")


# -------- partners and balance
@chart("partners", "pa_a_surplus_deficit", "أكبر فائض وأكبر عجز مع الدول", "Biggest surplus and deficit partners")
def surplus_deficit(t, lang, style, n=6):
    b = t.balance_by_country(t.year).sort_values(ascending=False)
    s = pd.concat([b.head(n), b.tail(n)])
    return cv.barplot([cname(i, lang) for i in s.index], s.round(1).tolist(), horizontal=True, sort=None,
                      highlight=gains(s), flags=flag_names(s.index), value_format="{:+,.1f}",
                      title=T(lang, f"الميزان التجاري مع الدول: أكبر فائض وأكبر عجز {t.year}",
                              f"Trade balance by partner: biggest surplus and deficit, {t.year}"),
                      subtitle=T(lang, "موجب = فائض، سالب = عجز · مليون دينار", "positive = surplus, negative = deficit · JD million"),
                      **style)


@chart("partners", "pa_b_exports_vs_imports", "الصادرات مقابل المستوردات لأهم الشركاء", "Exports vs imports, top partners")
def exports_vs_imports(t, lang, style, n=8):
    L = LABELS[lang]
    top = t.by_country(None, t.year).head(n).index
    d = t.rows(t.year, isos=top)
    exp = d[d["flow"] != "imports"].groupby("iso")["value"].sum()
    imp = d[d["flow"] == "imports"].groupby("iso")["value"].sum()
    return cv.multibarplot([cname(i, lang) for i in top],
                           {L["total_exports"]: [float(exp.get(i, 0)) for i in top], L["imports"]: [float(imp.get(i, 0)) for i in top]},
                           label_wrap=12, title=T(lang, f"أهم الشركاء التجاريين: الصادرات والمستوردات {t.year}",
                                                  f"Top trading partners: exports and imports, {t.year}"),
                           subtitle=L["unit"], **style)


@chart("partners", "pa_c_heatmap", "أهم الشركاء عبر السنوات (خريطة حرارية)", "Top partners over the years (heatmap)")
def partners_heatmap(t, lang, style, n=10):
    top = t.by_country(None, t.year).head(n).index
    g = t.rows(isos=top).groupby(["iso", "year"])["value"].sum()
    tab = pd.DataFrame({str(y): [float(g.get((i, y), 0)) for i in top] for y in t.years},
                       index=[cname(i, lang) for i in top])
    return cv.heatmap(tab, value_format="{:,.0f}",
                      title=T(lang, f"حجم التجارة مع أهم الشركاء {t.years[0]}–{t.year}", f"Trade with the top partners, {t.years[0]}–{t.year}"),
                      subtitle=T(lang, "إجمالي التجارة · مليون دينار", "total trade · JD million"), **style)


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


def _goods_changes(t, lang, style, flow, title_ar, title_en, n=5):
    now, before = t.by_goods(flow, t.year, lang), t.by_goods(flow, t.prev, lang)
    diff = now.sub(before, fill_value=0).sort_values(ascending=False)
    s = pd.concat([diff.head(n), diff.tail(n)])
    s = s[~s.index.duplicated()]
    return cv.barplot(s.index.tolist(), s.round(1).tolist(), horizontal=True, sort=None, highlight=gains(s), flags=False,
                      value_format="{:+,.1f}", title=T(lang, title_ar, title_en),
                      subtitle=T(lang, f"التغير بالمليون دينار، {t.year} مقارنة مع {t.prev}",
                                 f"change in JD million, {t.year} vs {t.prev}"), **style)


def _goods_heatmap(t, lang, style, flow, title_ar, title_en, n=8):
    top = t.by_goods(flow, t.year, lang).head(n).index
    col = f"goods_{lang}"
    g = t.rows(flow=flow).groupby([col, "year"])["value"].sum()
    tab = pd.DataFrame({str(y): [float(g.get((name, y), 0)) for name in top] for y in t.years}, index=list(top))
    return cv.heatmap(tab, value_format="{:,.0f}", title=T(lang, title_ar, title_en),
                      subtitle=LABELS[lang]["unit"], **style)


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


@chart("export_goods", "4d_biggest_changes", "أكبر زيادة وأكبر تراجع", "Biggest gains and falls")
def export_goods_changes(t, lang, style):
    return _goods_changes(t, lang, style, "national", "أكبر تغير في السلع المصدرة", "Exported goods: biggest gains and falls")


@chart("export_goods", "4e_heatmap", "أهم السلع عبر السنوات (خريطة حرارية)", "Top goods over the years (heatmap)")
def export_goods_heatmap(t, lang, style):
    return _goods_heatmap(t, lang, style, "national", f"أهم السلع المصدرة {t.years[0]}–{t.year}",
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


@chart("import_goods", "5d_biggest_changes", "أكبر زيادة وأكبر تراجع", "Biggest gains and falls")
def import_goods_changes(t, lang, style):
    return _goods_changes(t, lang, style, "imports", "أكبر تغير في السلع المستوردة", "Imported goods: biggest gains and falls")


@chart("import_goods", "5e_heatmap", "أهم السلع عبر السنوات (خريطة حرارية)", "Top goods over the years (heatmap)")
def import_goods_heatmap(t, lang, style):
    return _goods_heatmap(t, lang, style, "imports", f"أهم السلع المستوردة {t.years[0]}–{t.year}",
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
    vals = [round(t.indicators(t.year, k)["balance"], 1) for k in keys]
    return cv.barplot([short[k] for k in keys], vals, highlight=gains(vals), flags=False,
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
    def trend(t, lang, style):
        L = LABELS[lang]
        series = {L[k]: [t.indicators(y, key)[k] for y in t.years] for k in ("national", "reexports", "imports")}
        return cv.lineplot([str(y) for y in t.years], series,
                           title=T(lang, f"التجارة مع {ar} {t.years[0]}–{t.year}", f"Trade with {en}, {t.years[0]}–{t.year}"),
                           subtitle=L["unit"], **style)

    CHARTS.append(("bloc_detail", f"7{key}_d_map", f"{ar}: الخريطة", f"{en}: map", map_))
    CHARTS.append(("bloc_detail", f"7{key}_e_trend", f"{ar}: عبر السنوات", f"{en}: over the years", trend))


for _key in ("gafta", "asia", "nafta", "eu"):
    _bloc_charts(_key)


# -------- the Americas: north and south on their own maps
def _area_map(t, lang, style, isos, region, title_ar, title_en, ranking=False):
    s = t.by_country(None, t.year, isos=isos)
    return cv.geoplot([cname(i, lang) for i in s.index], s.round(1).tolist(), region=region,
                      label_top=3 if ranking else 6, ranking=ranking, ranking_top=8,
                      title=T(lang, title_ar, title_en),
                      subtitle=T(lang, "إجمالي التجارة · مليون دينار", "total trade · JD million"), **style)


@chart("americas", "am_a_north_map", "خريطة أمريكا الشمالية", "North America map")
def north_america_map(t, lang, style):
    return _area_map(t, lang, style, NAFTA, "north_america", f"التجارة مع دول أمريكا الشمالية {t.year}",
                     f"Trade with North America, {t.year}")


@chart("americas", "am_b_south_map", "خريطة أمريكا الجنوبية", "South America map")
def south_america_map(t, lang, style):
    return _area_map(t, lang, style, SOUTH_AMERICA, "south_america", f"التجارة مع دول أمريكا الجنوبية {t.year}",
                     f"Trade with South America, {t.year}", ranking=True)


@chart("americas", "am_c_north_vs_south", "الشمال مقابل الجنوب", "North vs South")
def north_vs_south(t, lang, style):
    L = LABELS[lang]
    keys = ["national", "reexports", "imports"]
    north, south = t.indicators(t.year, isos=NAFTA), t.indicators(t.year, isos=SOUTH_AMERICA)
    return cv.multibarplot([L[k] for k in keys], {T(lang, "أمريكا الشمالية", "North America"): [north[k] for k in keys],
                                                  T(lang, "أمريكا الجنوبية", "South America"): [south[k] for k in keys]},
                           title=T(lang, f"التجارة مع أمريكا الشمالية وأمريكا الجنوبية {t.year}",
                                   f"Trade with North and South America, {t.year}"), subtitle=L["unit"], **style)


@chart("americas", "am_d_south_partners", "أهم شركاء أمريكا الجنوبية", "Top South American partners")
def south_partners(t, lang, style):
    s = t.by_country(None, t.year, isos=SOUTH_AMERICA).head(TOP)
    return cv.barplot([cname(i, lang) for i in s.index], s.round(1).tolist(), flags=flag_names(s.index),
                      title=T(lang, f"أهم الشركاء التجاريين في أمريكا الجنوبية {t.year}", f"Top partners in South America, {t.year}"),
                      subtitle=T(lang, "إجمالي التجارة · مليون دينار", "total trade · JD million"), **style)


# -------- regional maps of total trade
def _total_region(region, slug, cap_ar, cap_en, place_ar, place_en):
    def fn(t, lang, style):
        s = in_region(t.by_country(None, t.year), region)
        return cv.geoplot([cname(i, lang) for i in s.index], s.round(1).tolist(), region=region,
                          title=T(lang, f"التجارة مع {place_ar} {t.year}", f"Trade with {place_en}, {t.year}"),
                          subtitle=T(lang, "إجمالي التجارة · مليون دينار", "total trade · JD million"), **style)
    CHARTS.append(("regions", slug, cap_ar, cap_en, fn))


_total_region("middle_east", "rg_a_middle_east", "الشرق الأوسط", "Middle East", "دول الشرق الأوسط", "the Middle East")
_total_region("gcc", "rg_b_gcc", "دول الخليج", "Gulf states", "دول الخليج العربي", "the Gulf states")
_total_region("asia", "rg_c_asia", "آسيا", "Asia", "دول آسيا", "Asia")
_total_region("europe", "rg_d_europe", "أوروبا", "Europe", "دول أوروبا", "Europe")
_total_region("africa", "rg_e_africa", "أفريقيا", "Africa", "دول أفريقيا", "Africa")


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
        if any((lang, design, slug) in done or (out / lang / design / f"{slug}.png").exists()
               for lang in langs for design in designs):   # a run with --only keeps the other sections
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
    for section in (s for s in SECTIONS if s in cards):
        items = cards[section]
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
    order = list(SECTIONS)
    todo = sorted((c for c in CHARTS if not args.only or c[0] in args.only), key=lambda c: order.index(c[0]))
    print(f"{t.path.name}: {t.years[0]}–{t.year}, report year {t.year} vs {t.prev} · {len(todo)} charts × "
          f"{len(args.designs)} designs × {len(args.lang)} languages")
    if t.unknown:
        print("  countries without a map position:", ", ".join(t.unknown))
    done, failed, started = set(), [], time.perf_counter()
    for lang in args.lang:
        for design in args.designs:
            folder = out / lang / design
            folder.mkdir(parents=True, exist_ok=True)
            logo = logo_for(design, out)
            style = dict(design=design, figure_size=SIZE, logo=logo, logo_alignment=LOGO_CORNER, logo_size=LOGO_SIZE)
            # the PDF holds every chart, so a run with --only leaves the existing PDF alone
            pdf = None if args.only else PdfPages(folder / f"acc_trade_charts_{lang}_{design}.pdf")
            for section, slug, *_, fn in todo:
                try:
                    c = fn(t, lang, style)
                    c.save(str(folder / f"{slug}.png"), dpi=DPI)
                    if pdf:
                        pdf.savefig(c.fig)
                    c.close()
                    done.add((lang, design, slug))
                except Exception as exc:
                    failed.append(f"{lang}/{design}/{slug}: {type(exc).__name__}: {exc}")
            if pdf:
                pdf.close()
            print(f"  {lang} · {design}: {sum(1 for d in done if d[:2] == (lang, design))} charts")
    gallery(out, t, args.lang, args.designs, done)
    print(f"{len(done)} images in {time.perf_counter() - started:.0f}s · open {out / 'index.html'}")
    for f in failed:
        print("  ✗", f)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
