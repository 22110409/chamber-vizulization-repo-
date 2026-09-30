"""Chamber Studio: a Power BI-style dashboard on top of chamberviz.

The logic lives in plain modules (no Streamlit), so it can be tested and used from scripts:
  data       load and clean files, column types, rename / hide, joins
  filters    filter specs (JSON) and apply_filters(df, spec)
  measures   aggregations, quick calculations, safe calculated columns
  regions    country -> region for drill-down
"""
__version__ = "0.1.0"
