"""Foreign-trade report: the fixed set of charts for the trade dataset, drawn in one run.

    python reports/trade_report.py                    # the sample data -> reports/output/
    python reports/trade_report.py my_data.xlsx       # your file
    python reports/trade_report.py my_data.xlsx --only 02 05

The data file has one sheet per subject (names in SHEETS below). In every sheet the first text
column holds the names (indicator, country, commodity, bloc) and the year columns (2024, 2025, ...)
hold the values. The newest year column is the report year, the one before it the comparison year,
so next year's file (with a 2026 column) needs no change here.

To change a chart: edit its function below (each one is a few lines).
To add a chart: copy a function, give it a new number in @chart(...).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

import chamberviz as cv  # noqa: E402

HERE = Path(__file__).resolve().parent

# ============================================================== settings (edit here)
DATA = HERE.parent / "examples" / "sample_trade_report.xlsx"
OUT = HERE / "output"
DESIGN = "report_slate"            # white, navy title, gold line, slate bars, gold highlight
SIZE = (12, 6.75)                  # inches (16:9)
DPI = 200
UNIT = "مليون دينار"
TOP = 7                            # how many countries / goods in the "top" charts

SHEETS = {                         # what each sheet is called in the file
    "indicators": "المؤشرات",
    "import_sources": "المستوردات حسب الدولة",
    "export_goods": "السلع المصدرة",
    "import_goods": "السلع المستوردة",
    "blocs": "التكتلات الاقتصادية",
}
INDICATORS = {                     # the rows of the indicators sheet
    "exports": "الصادرات الوطنية",
    "reexports": "إعادة التصدير",
    "total_exports": "إجمالي الصادرات",
    "imports": "المستوردات",
    "total_trade": "إجمالي التجارة الخارجية",
    "balance": "الميزان التجاري",
}
BLOC_COLORS = ["#1f3a5f", "#d9a92a", "#3f7f5a", "#b84a45", "#7a6ab0", "#5f7a88"]
STYLE = dict(design=DESIGN, figure_size=SIZE, logo=None)


# ============================================================== reading the data
class Data:
    def __init__(self, path):
        self.path = Path(path)
        self.book = cv.read_excel(self.path)
        years = self.years("indicators")
        if len(years) < 1:
            raise SystemExit(f"No year columns (like 2024, 2025) in the sheet '{SHEETS['indicators']}'.")
        self.year = years[-1]
        self.prev = years[-2] if len(years) > 1 else None

    def sheet(self, key):
        name = SHEETS[key]
        if name not in self.book:
            raise KeyError(f"the file has no sheet '{name}' (it has: {', '.join(self.book)})")
        return self.book[name]

    def years(self, key) -> list[str]:
        df = self.sheet(key)
        return sorted((str(c) for c in df.columns if re.fullmatch(r"\d{4}", str(c).strip())), key=int)

    def table(self, key):
        """The sheet indexed by its name column, with only the year columns (as numbers)."""
        df = self.sheet(key)
        name_col = next(c for c in df.columns if not str(c).strip().isdigit())
        cols = [c for c in df.columns if str(c).strip() in self.years(key)]
        t = df.set_index(name_col)[cols]
        t.columns = [str(c).strip() for c in t.columns]
        return t.apply(lambda s: s.astype(float))

    def values(self, key, year=None, top=None):
        """One year's values, largest first."""
        s = self.table(key)[year or self.year].dropna().sort_values(ascending=False)
        return s.head(top) if top else s

    def indicator(self, name, year=None):
        return float(self.table("indicators").loc[INDICATORS[name], year or self.year])


def pct(new, old):
    return round((new / old - 1) * 100, 1) if old else None


# ============================================================== the charts
CHARTS = []


def chart(number, name):
    def register(fn):
        CHARTS.append((number, name, fn))
        return fn
    return register


@chart("01", "indicators")
def indicators(d: Data):
    t = d.table("indicators")
    return cv.multibarplot(list(t.index), {d.prev: t[d.prev].tolist(), d.year: t[d.year].tolist()},
                           title=f"مؤشرات التجارة الخارجية: {d.year} مقارنة مع {d.prev}", subtitle=UNIT, **STYLE)


@chart("02", "top_import_sources")
def top_import_sources(d: Data):
    s = d.values("import_sources", top=TOP)
    return cv.barplot(list(s.index), s.tolist(), flags=False, title=f"أهم مصادر المستوردات {d.year}",
                      subtitle=UNIT, **STYLE)


@chart("03", "top_export_goods")
def top_export_goods(d: Data):
    s = d.values("export_goods", top=TOP)
    return cv.barplot(list(s.index), s.tolist(), flags=False, title=f"أهم السلع المصدرة {d.year}",
                      subtitle=UNIT, **STYLE)


@chart("04", "top_import_goods")
def top_import_goods(d: Data):
    s = d.values("import_goods", top=TOP)
    return cv.barplot(list(s.index), s.tolist(), flags=False, title=f"أهم السلع المستوردة {d.year}",
                      subtitle=UNIT, **STYLE)


@chart("05", "trade_by_bloc")
def trade_by_bloc(d: Data):
    s = d.values("blocs")
    return cv.pieplot(list(s.index), s.tolist(), colors=BLOC_COLORS, show_values=False, flags=False,
                      center_text="التجارة الخارجية", center_label="",
                      title=f"التجارة الخارجية حسب التكتل الاقتصادي {d.year}", **STYLE)


@chart("06", "import_sources_vs_last_year")
def import_sources_vs_last_year(d: Data):
    t = d.table("import_sources").sort_values(d.year, ascending=False).head(TOP)
    return cv.multibarplot(list(t.index), {d.prev: t[d.prev].tolist(), d.year: t[d.year].tolist()},
                           title=f"أهم مصادر المستوردات: {d.year} مقارنة مع {d.prev}", subtitle=UNIT, **STYLE)


@chart("07", "export_goods_vs_last_year")
def export_goods_vs_last_year(d: Data):
    t = d.table("export_goods").sort_values(d.year, ascending=False).head(TOP)
    return cv.multibarplot(list(t.index), {d.prev: t[d.prev].tolist(), d.year: t[d.year].tolist()},
                           title=f"أهم السلع المصدرة: {d.year} مقارنة مع {d.prev}", subtitle=UNIT, **STYLE)


@chart("08", "import_goods_vs_last_year")
def import_goods_vs_last_year(d: Data):
    t = d.table("import_goods").sort_values(d.year, ascending=False).head(TOP)
    return cv.multibarplot(list(t.index), {d.prev: t[d.prev].tolist(), d.year: t[d.year].tolist()},
                           title=f"أهم السلع المستوردة: {d.year} مقارنة مع {d.prev}", subtitle=UNIT, **STYLE)


@chart("09", "indicators_change")
def indicators_change(d: Data):
    # the trade balance is left out: a % change of a deficit reads the wrong way round
    names = [n for k, n in INDICATORS.items() if k != "balance"]
    t = d.table("indicators").loc[names]
    change = [pct(t.loc[n, d.year], t.loc[n, d.prev]) for n in names]
    return cv.barplot(names, change, highlight=None, flags=False, value_format="{:+.1f}%",
                      title=f"نسبة التغير في مؤشرات التجارة الخارجية {d.year} مقارنة مع {d.prev}",
                      subtitle="%", **STYLE)


@chart("10", "import_sources_change")
def import_sources_change(d: Data):
    t = d.table("import_sources").sort_values(d.year, ascending=False).head(TOP)
    change = [(c, pct(t.loc[c, d.year], t.loc[c, d.prev])) for c in t.index]
    change.sort(key=lambda x: -(x[1] or 0))
    return cv.barplot([c for c, _ in change], [v for _, v in change], highlight=None, flags=False,
                      value_format="{:+.1f}%",
                      title=f"نسبة التغير في المستوردات من أهم المصادر {d.year} مقارنة مع {d.prev}",
                      subtitle="%", **STYLE)


@chart("11", "key_figures")
def key_figures(d: Data):
    cards = []
    for key, icon in (("exports", "package-export"), ("reexports", "refresh"), ("imports", "package-import"),
                      ("balance", "scale")):
        now = d.indicator(key)
        change = pct(now, d.indicator(key, d.prev)) if d.prev and key != "balance" else None
        cards.append({"label": INDICATORS[key], "value": now, "unit": UNIT, "change": change, "icon": icon})
    return cv.kpi_cards(cards, decimals=1, title=f"أبرز مؤشرات التجارة الخارجية {d.year}",
                        subtitle=f"التغير مقارنة مع {d.prev}" if d.prev else None, **STYLE)


@chart("12", "import_sources_share")
def import_sources_share(d: Data):
    top = d.values("import_sources", top=5)
    rest = d.indicator("imports") - top.sum()     # every other country, from the total imports
    labels, values = list(top.index), top.tolist()
    if rest > 0:
        labels.append("دول أخرى")
        values.append(rest)
    return cv.pieplot(labels, values, colors=BLOC_COLORS, show_values=False, flags=False, sort=None,
                      center_text="المستوردات", center_label="",
                      title=f"حصة أهم مصادر المستوردات من إجمالي المستوردات {d.year}", **STYLE)


@chart("13", "import_sources_map")
def import_sources_map(d: Data):
    s = d.values("import_sources")
    return cv.geoplot(list(s.index), s.tolist(), title=f"مصادر المستوردات على الخريطة {d.year}",
                      subtitle=UNIT, **STYLE)


@chart("14", "export_goods_structure")
def export_goods_structure(d: Data):
    s = d.values("export_goods")
    return cv.treemap(list(s.index), s.tolist(), flags=False, colors=None,
                      title=f"هيكل الصادرات السلعية {d.year}", subtitle=UNIT, **STYLE)


# ============================================================== run
def main(argv=None):
    ap = argparse.ArgumentParser(description="Draw the fixed trade report charts.")
    ap.add_argument("data", nargs="?", default=str(DATA), help="the Excel file (default: the sample)")
    ap.add_argument("--out", default=str(OUT), help="folder for the PNG files and the PDF")
    ap.add_argument("--only", nargs="*", help="chart numbers to draw, e.g. --only 01 05")
    args = ap.parse_args(argv)

    d = Data(args.data)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    todo = [c for c in CHARTS if not args.only or c[0] in args.only]
    print(f"{d.path.name}: report year {d.year}, compared with {d.prev} · {len(todo)} charts -> {out}")
    done, failed = [], []
    pdf_path = out / f"trade_report_{d.year}.pdf"
    with PdfPages(pdf_path) as pdf:
        for number, name, fn in todo:
            try:
                c = fn(d)
                png = out / f"{number}_{name}.png"
                c.save(str(png), dpi=DPI)
                pdf.savefig(c.fig)
                c.close()
                done.append(png)
                print(f"  ✓ {number} {name}")
            except Exception as exc:
                failed.append(number)
                print(f"  ✗ {number} {name}: {exc}")
    print(f"{len(done)} charts saved, all of them also in {pdf_path.name}" +
          (f" · {len(failed)} failed: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
