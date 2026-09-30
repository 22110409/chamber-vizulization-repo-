# chamberviz

Branded charts in one line of Python, with country flags, 5,000+ icons, Arabic support and your
logo on every chart. It also has a **dynamic mode**: give it an Excel file and it suggests the
right charts, draws them, and gives you the code.

```python
import chamberviz as cv

cv.barplot(countries, values,
           figure_size=(12, 8), design="navy_gold",
           bars=None, background_color=None, background_image=None,
           logo="logo.png", logo_alignment=("top", "right"),
           title="Top import sources 2025", subtitle="JD million",
           save="chart.png")
```

![bar chart](docs/gallery/bar_flags.jpg)

---

## 1. Install

```bash
pip install -r requirements.txt       # matplotlib, pandas, openpyxl, pillow, arabic-reshaper, python-bidi
pip install -e .                      # installs "chamberviz" (run inside this folder)
```

Everything the charts need (fonts, 265 flags, icons, world maps) is inside the package. No internet needed.

## 2. Add the Amman Chamber logo once

```python
import chamberviz as cv
cv.set_default_logo("amman_chamber_logo.png")    # PNG with a transparent background works best
```

From then on **every chart gets the logo automatically** (top-right by default).
Use `logo=None` to hide it on one chart, `logo="other.png"` for a different one, or
`logo=["a.png", "b.png"], logo_alignment=["top-right", "bottom-left"]` for two logos.

---

## 3. Simple version (you choose the chart)

### Options that every chart accepts

| Option | Example | Meaning |
|---|---|---|
| `figure_size` | `(12, 8)` | size in inches (16×9 = slides, 10×10 = square post) |
| `design` | `"navy_gold"` | one of the designs below, or your own (`make_design`) |
| `title`, `subtitle` | `"Top imports"` | `sub_title` also works |
| `source` | `"Source: DoS"` | small line at the bottom |
| `background_color` | `"#0b1a3a"` or `("#top", "#bottom")` | flat colour or gradient |
| `background_image` | `"photo.jpg"` | picture behind the chart |
| `background_image_opacity` | `0.35` | how strongly the picture shows |
| `background_map` | `"solid"`, `"dots"`, `False` | faint world map behind the chart |
| `logo` | `"logo.png"` / `None` | default = your saved logo |
| `logo_alignment` | `"top-right"` or `("down", "left")` | top/bottom (or down) + left/right |
| `logo_size` | `0.10` | logo height as a share of the figure height |
| `title_alignment` | `"center"`, `"left"`, `"right"` | |
| `font_scale` | `1.2` | make all text bigger or smaller |
| `save` | `"chart.png"` | `.png`, `.jpg`, `.svg` or `.pdf` |
| `dpi`, `transparent` | `300`, `True` | output quality / transparent background |

Typos get a helpful message: `backgraound_color` → *Did you mean: background_color?*

### Designs

`navy_gold` · `royal_blue` · `ivory_dots` · `emerald_gold` · `desert_sand` · `minimal` · `charcoal_teal`

![designs](docs/designs_preview.png)

Make your own from any of them:

```python
cv.make_design("chamber", base="navy_gold", accent="#c8102e",
               highlight=("#6d0a18", "#e0313f"), title_color="#ffffff")
cv.set_defaults(design="chamber")           # use it for everything
```

### Chart types

| Function | What it draws | Extra options |
|---|---|---|
| `barplot(labels, values)` | vertical bars | `horizontal=True`, `bars=`, `highlight="max"`, `sort="desc"`, `top=10`, `flags=`, `icons=`, `ylabel=`, `rtl=True` |
| `multibarplot(cats, {"2024": [...], "2025": [...]})` | grouped bars | `stacked=True` |
| `pieplot(labels, values)` | donut / pie | `donut=False`, `max_slices=8`, `center_text=` |
| `lineplot(x, values)` or `lineplot(x, {"A": [...], "B": [...]})` | lines | `area=True`, `show_change=True`, `smooth=True` |
| `dotplot(labels, values, compare=old_values)` | lollipop / dumbbell | `names=("2024", "2025")` |
| `treemap(labels, values)` | shares as rectangles | `icons=`, `flags=` |
| `histplot(values)` | distribution | `bins=`, `show_mean`, `show_median` |
| `boxplot({"A": [...], "B": [...]})` | spread by group | `points=True` |
| `scatterplot(x, y, labels=countries)` | relationship (+ trend line) | `size=` for bubbles, `groups=` |
| `heatmap(table)` | grid of values | `rows=`, `columns=`, `values=` for long tables |
| `geoplot(countries, values)` | world / regional map | `region="middle_east"`, `style="bubbles"` |
| `flowmap(countries, values, hub="Jordan")` | arrows into Jordan + ranking | `direction="out"` for exports |
| `kpi_cards([{...}, {...}])` | headline numbers | `label, value, unit, change, icon, flag, note` |

Every chart also accepts a DataFrame: `cv.barplot(df, x="Country", y="Value")`, a dict
`{"A": 1, "B": 2}` or a pandas Series. Numbers: `decimals=1`, `value_prefix="JD "`,
`value_suffix="%"`, `compact=True` (1.2M).

Regions for maps: `world, middle_east, mena, arab_world, gcc, levant, europe, asia, africa, americas`
or your own `(lon_min, lon_max, lat_min, lat_max)`.

### Flags

Flags appear automatically when the labels are countries (English, Arabic, ISO codes, and common
spellings like "الصين الشعبية", "الأمارات العربية", "KSA", "UAE", "Korea, Republic of").

```python
cv.country_code("السعودية")      # 'SA'
cv.flag("Jordan", "round")       # image array; "rect" for rectangular flags
cv.flag_path("Egypt")            # PNG file path, to use anywhere
cv.flag_sheet()                  # flags.png with all 265 flags and their codes
```

`flags=False` turns them off; `flags=["China", "Iraq", ...]` sets them yourself; `flag_style="rect"`.

### Icons (5,229 outline + 1,057 filled, from Tabler Icons)

```python
cv.search_icons("truck")         # ['firetruck', 'rv-truck', 'truck', 'truck-delivery', ...]
cv.icon_sheet("medical")         # picture of all matching icons, with names
cv.barplot(labels, values, icons=["flame", "car", "diamond", "atom", "bolt", "wheat", "bottle"])
cv.barplot(labels, values, icons="auto")   # guesses from the words (English + Arabic)
```

### Arabic

Just use Arabic text; letters are joined and written right to left automatically. For horizontal
bars, `rtl=True` puts the labels on the right. Donut and flow-map legends switch sides by themselves.

### Defaults for everything

```python
cv.set_defaults(design="ivory_dots", figure_size=(12, 8), logo_alignment="top-left",
                source="Source: Amman Chamber of Industry", dpi=300)
```

---

## 4. Dynamic version (it suggests charts from Excel)

```python
cv.suggest("trade.xlsx")                       # ranked ideas, with the reason for each
ideas = cv.suggest("trade.xlsx", verbose=False)
ideas[0].render(design="ivory_dots").save("best.png")
print(ideas[0].code())                         # the simple-version code for that chart

cv.auto("trade.xlsx", out_dir="charts", top=4, design="navy_gold")   # draws them + report.html
```

It handles real-world Excel sheets: finds the header row under title rows, turns "2,890" text into
numbers, removes empty rows/columns and **Total / المجموع** rows, and understands Arabic headers.

How it decides:

| The sheet has… | It suggests |
|---|---|
| a category + a number (≤ 12 items) | bar chart (flags if countries, icons if it recognises the items) |
| many categories or long names | horizontal bars (top 15), lollipop |
| parts of a whole (≤ 7 items, or a "Share %" column) | donut |
| countries | world/regional map, bubble map, flow map into Jordan |
| a date/year column | line chart, area chart, bars per period |
| one column per year (2021, 2022, …) | multi-line trend, dumbbell first vs last year, grouped bars, heatmap |
| two categories + a number | grouped / stacked bars, heatmap |
| two numbers | scatter plot (scored by correlation) |
| many rows of one number | histogram, box plot |
| always | KPI cards with the headline numbers |

### Upload app (no code)

```bash
pip install streamlit
python -m chamberviz app
```

Upload an Excel file → pick a sheet → choose a suggestion (or build your own chart) → change design,
logo, logo position, background colour/image, title → download PNG or PDF, and copy the code.

### Command line

```bash
python -m chamberviz suggest trade.xlsx
python -m chamberviz auto trade.xlsx -o charts --design ivory_dots --logo-alignment top-left
python -m chamberviz designs          # designs_preview.png
python -m chamberviz icons truck      # icons_truck.png + names
python -m chamberviz flags --arabic   # flags.png with Arabic names
python -m chamberviz logo amman_chamber_logo.png
```

---

## 5. Gallery

| | |
|---|---|
| ![](docs/gallery/bar_icons.jpg) | ![](docs/gallery/bar_arabic.jpg) |
| ![](docs/gallery/barh.jpg) | ![](docs/gallery/barh_arabic_rtl.jpg) |
| ![](docs/gallery/donut_icons.jpg) | ![](docs/gallery/donut_flags.jpg) |
| ![](docs/gallery/line.jpg) | ![](docs/gallery/multi_line.jpg) |
| ![](docs/gallery/dumbbell.jpg) | ![](docs/gallery/treemap.jpg) |
| ![](docs/gallery/map_world.jpg) | ![](docs/gallery/map_region.jpg) |
| ![](docs/gallery/flow_map.jpg) | ![](docs/gallery/flow_map_arabic.jpg) |
| ![](docs/gallery/kpi_cards.jpg) | ![](docs/gallery/scatter_flags.jpg) |
| ![](docs/gallery/grouped.jpg) | ![](docs/gallery/stacked.jpg) |
| ![](docs/gallery/histogram.jpg) | ![](docs/gallery/boxplot.jpg) |
| ![](docs/gallery/heatmap.jpg) | ![](docs/gallery/background_image.jpg) |

Numbers in the examples are sample figures for demonstration only.

## 6. Files

```
chamberviz/            the library
  charts_bar.py        bar, horizontal bar, grouped/stacked, dot/dumbbell, treemap
  charts_stats.py      donut, line/area, histogram, box, scatter, heatmap
  charts_geo.py        maps and flow maps
  charts_kpi.py        KPI cards
  canvas.py            background, map, title, logo, source (shared by every chart)
  themes.py            the designs
  suggest.py, auto.py  the dynamic Excel engine and HTML report
  app.py               the upload app
  assets/              fonts, flags, icons, maps, logos
examples/              simple_examples.py, dynamic_example.py, sample_trade_data.xlsx
docs/                  gallery and previews
```

---

## بالعربي باختصار

- **مرة واحدة فقط:** `cv.set_default_logo("شعار_الغرفة.png")` وسيظهر الشعار على كل رسم تلقائياً.
- **النسخة البسيطة:** `cv.barplot(الأسماء, القيم, design="navy_gold", title="...", logo_alignment=("top","right"), save="chart.png")`
- **النسخة الذكية:** `cv.suggest("ملف.xlsx")` تقترح أنسب الرسوم مع السبب، و`cv.auto("ملف.xlsx")` ترسمها وتنشئ تقريراً فيه الكود.
- **بدون كود:** `python -m chamberviz app` ثم ارفع ملف الإكسل من المتصفح.
- الأعلام تظهر تلقائياً عندما تكون الأسماء دولاً (بالعربي أو الإنجليزي)، والأيقونات عبر `icons="auto"` أو بالاسم.
