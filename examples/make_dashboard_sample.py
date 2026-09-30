"""Sample data for Chamber Studio (synthetic figures, not official statistics).

    python examples/make_dashboard_sample.py          -> examples/sample_trade_dashboard.xlsx
    python examples/make_dashboard_sample.py --big    -> also examples/sample_trade_500k.csv

Sheets
  Trade       Month | Country | Commodity | Flow | Value (JD thousand) | Weight (tonnes)   (36 months)
  Countries   Country | Arabic name | Population (million)                                 (for joins)
  التجارة     the same trade data with Arabic column names and values
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
rng = np.random.default_rng(42)

# country: (Arabic, size of trade, population in millions)
COUNTRIES = {
    "China": ("الصين", 100, 1410), "Saudi Arabia": ("السعودية", 72, 36), "United States": ("الولايات المتحدة", 60, 335),
    "United Arab Emirates": ("الإمارات", 30, 10), "Germany": ("ألمانيا", 18, 84), "Egypt": ("مصر", 17, 112),
    "India": ("الهند", 22, 1430), "Turkey": ("تركيا", 15, 86), "Italy": ("إيطاليا", 10, 59), "Iraq": ("العراق", 21, 45),
    "Kuwait": ("الكويت", 7, 4.3), "Syria": ("سوريا", 5, 23), "Qatar": ("قطر", 6, 2.7), "Lebanon": ("لبنان", 4, 5.3),
    "Palestine": ("فلسطين", 5, 5.4), "Oman": ("عُمان", 3, 4.6), "Bahrain": ("البحرين", 2.5, 1.5),
    "France": ("فرنسا", 7, 68), "Spain": ("إسبانيا", 5, 48), "Japan": ("اليابان", 8, 124),
    "South Korea": ("كوريا الجنوبية", 9, 52), "Indonesia": ("إندونيسيا", 6, 278), "Brazil": ("البرازيل", 4, 216),
    "Canada": ("كندا", 3, 40), "Morocco": ("المغرب", 3, 37),
}
# commodity: (Arabic, share of imports, share of exports, share of re-exports)
COMMODITIES = {
    "Mineral fuels": ("الوقود المعدني", 0.20, 0.02, 0.08), "Vehicles": ("المركبات", 0.16, 0.02, 0.30),
    "Machinery": ("الآلات", 0.13, 0.04, 0.14), "Electrical equipment": ("الأجهزة الكهربائية", 0.08, 0.05, 0.12),
    "Pearls & gold": ("اللؤلؤ والذهب", 0.12, 0.08, 0.05), "Cereals": ("الحبوب", 0.07, 0.01, 0.03),
    "Pharmaceuticals": ("الأدوية", 0.05, 0.12, 0.08), "Garments": ("الألبسة", 0.03, 0.28, 0.05),
    "Fertilizers": ("الأسمدة", 0.01, 0.18, 0.01), "Vegetables & fruit": ("الخضار والفواكه", 0.04, 0.09, 0.04),
    "Plastics": ("اللدائن", 0.06, 0.05, 0.06), "Iron & steel": ("الحديد والصلب", 0.05, 0.06, 0.04),
}
FLOWS = {"Imports": ("المستوردات", 0), "Exports": ("الصادرات", 1), "Re-exports": ("المعاد تصديره", 2)}
EXPORT_TILT = {"United States": 2.2, "India": 1.8, "Iraq": 2.5, "Saudi Arabia": 1.2, "Syria": 1.5, "Palestine": 2.0,
               "Kuwait": 1.4, "Qatar": 1.6, "Lebanon": 1.5, "China": 0.15, "Germany": 0.2, "Italy": 0.3}
MONTHS = pd.date_range("2023-01-01", "2025-12-01", freq="MS")
SEASON = np.array([0.94, 0.90, 1.00, 1.02, 1.00, 0.97, 0.98, 1.03, 1.00, 1.05, 1.02, 1.09])


def trade(months=MONTHS, density=0.72) -> pd.DataFrame:
    rows = []
    for country, (_, size, _) in COUNTRIES.items():
        for commodity, (_, *shares) in COMMODITIES.items():
            for flow, (_, k) in FLOWS.items():
                tilt = EXPORT_TILT.get(country, 0.8) if k else 1.0
                base = size * shares[k] * tilt * (1.0 if k == 0 else 0.45 if k == 1 else 0.12) * 900
                if base < 1 or rng.random() > density:
                    continue
                for i, m in enumerate(months):
                    growth = 1.045 ** (i / 12)
                    value = base * SEASON[m.month - 1] * growth * rng.lognormal(0, 0.18)
                    rows.append((m, country, commodity, flow, round(value, 1), round(value * rng.uniform(0.3, 2.5), 1)))
    return pd.DataFrame(rows, columns=["Month", "Country", "Commodity", "Flow", "Value (JD thousand)", "Weight (tonnes)"])


def countries() -> pd.DataFrame:
    return pd.DataFrame([(c, ar, pop) for c, (ar, _, pop) in COUNTRIES.items()],
                        columns=["Country", "Arabic name", "Population (million)"])


def arabic(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "الشهر": df["Month"],
        "الدولة": df["Country"].map({k: v[0] for k, v in COUNTRIES.items()}),
        "السلعة": df["Commodity"].map({k: v[0] for k, v in COMMODITIES.items()}),
        "نوع التجارة": df["Flow"].map({k: v[0] for k, v in FLOWS.items()}),
        "القيمة (ألف دينار)": df["Value (JD thousand)"],
    })


def big(n=500_000) -> pd.DataFrame:
    """n rows with the same columns (for speed tests)."""
    base = trade(density=1.0)
    reps = int(np.ceil(n / len(base)))
    out = pd.concat([base] * reps, ignore_index=True).head(n)
    out["Value (JD thousand)"] = (out["Value (JD thousand)"] * rng.lognormal(0, 0.1, len(out))).round(1)
    return out


if __name__ == "__main__":
    t = trade()
    out = HERE / "sample_trade_dashboard.xlsx"
    with pd.ExcelWriter(out) as xl:
        t.to_excel(xl, sheet_name="Trade", index=False)
        countries().to_excel(xl, sheet_name="Countries", index=False)
        arabic(t).to_excel(xl, sheet_name="التجارة", index=False)
    print(f"{out.name}: {len(t):,} trade rows")
    if "--big" in sys.argv:
        b = big()
        path = HERE / "sample_trade_500k.csv"
        b.to_csv(path, index=False)
        print(f"{path.name}: {len(b):,} rows")
