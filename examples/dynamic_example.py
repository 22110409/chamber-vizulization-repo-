"""DYNAMIC VERSION - give it an Excel file, it suggests charts and draws them.

Run:  python examples/dynamic_example.py
Or in a terminal:
      python -m chamberviz suggest examples/sample_trade_data.xlsx
      python -m chamberviz auto examples/sample_trade_data.xlsx -o charts --design ivory_dots
      python -m chamberviz app          # upload page in the browser (pip install streamlit)
"""
import chamberviz as cv

FILE = "examples/sample_trade_data.xlsx"
LOGO = "chamberviz/assets/logos/demo_logo.png"

# 1) What is in the file?
for sheet in cv.analyze(FILE):
    print(sheet.summary())

# 2) Ranked suggestions with the reason for each one
ideas = cv.suggest(FILE)

# 3) Draw one suggestion, in any design, and print the code that makes it
best = ideas[0]
best.render(design="ivory_dots", logo=LOGO).save("best_chart.png")
print("\nCode for this chart:\n" + best.code(design="ivory_dots"))

# 4) Or do everything: best 4 charts per sheet + charts/report.html
cv.auto(FILE, out_dir="charts", top=4, design="navy_gold", logo=LOGO, source="Source: sample data")
