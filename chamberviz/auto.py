"""Draw the suggested charts for an Excel file and write an HTML report with the code."""
from __future__ import annotations

import html
import re
import traceback
from pathlib import Path

import matplotlib.pyplot as plt

from .suggest import suggest


def _slug(s: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", str(s), flags=re.UNICODE).strip("_")
    return s[:50] or "chart"


def auto(file, out_dir="charts", *, sheet=None, top=4, design=None, report=True,
         min_score=0, verbose=True, **style):
    """Suggest charts for every sheet, draw the best `top` per sheet, and write report.html.

    cv.auto("trade.xlsx", out_dir="charts", design="ivory_dots", logo_alignment="top-left")
    Any chart option (design, logo, source, figure_size, ...) can be passed and applies to all.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sugs = [s for s in suggest(file, sheet, verbose=verbose) if s.score >= min_score]
    # pick the best `top` per sheet, preferring different chart types
    chosen = []
    for sheet_name in dict.fromkeys(s.sheet for s in sugs):
        ss = [s for s in sugs if s.sheet == sheet_name]
        picked, kinds = [], set()
        for s in ss:
            if len(picked) < top and s.chart not in kinds:
                picked.append(s)
                kinds.add(s.chart)
        for s in ss:  # fill up if there were not enough different types
            if len(picked) < top and s not in picked:
                picked.append(s)
        chosen += sorted(picked, key=lambda z: -z.score)
    if design:
        style["design"] = design
    results = []
    for i, s in enumerate(chosen, 1):
        fname = out / f"{i:02d}_{_slug(s.sheet)}_{s.chart}.png"
        try:
            ch = s.render(**style)
            ch.save(fname)
            ch.close()
            results.append((s, fname, None))
            if verbose:
                print(f"  saved {fname}")
        except Exception as e:  # keep going; report the problem
            plt.close("all")
            results.append((s, None, f"{type(e).__name__}: {e}"))
            if verbose:
                print(f"  could not draw {s.name} ({s.sheet}): {e}")
                traceback.print_exc(limit=2)
    if report:
        rp = _write_report(results, out, file, style.get("design"))
        if verbose:
            print(f"\nReport: {rp}")
    return results


def _write_report(results, out: Path, source, design) -> Path:
    cards = []
    for s, path, err in results:
        img = (f'<img src="{html.escape(path.name)}" alt="{html.escape(s.title)}">' if path
               else f'<div class="err">Could not draw this chart: {html.escape(err or "")}</div>')
        code = html.escape(s.code(design=design, save=path.name if path else "chart.png"))
        cards.append(f"""
<article class="card">
  <div class="head"><span class="kind">{html.escape(s.name)}</span>
    <span class="sheet">sheet: {html.escape(str(s.sheet))}</span>
    <span class="score" title="how well this chart fits the data"><progress value="{s.score:.0f}" max="100"></progress>{s.score:.0f}</span></div>
  {img}
  <h3>{html.escape(s.title)}</h3>
  <p>{html.escape(s.reason)}</p>
  <details><summary>Python code for this chart</summary><pre><code>{code}</code></pre></details>
</article>""")
    src = html.escape(str(source)) if not hasattr(source, "shape") else "DataFrame"
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Chart suggestions</title>
<style>
:root {{ --bg:#f4f5f7; --card:#fff; --ink:#1f2937; --muted:#6b7280; --accent:#b8862e; --line:#e5e7eb; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0f141c; --card:#171e29; --ink:#e5e7eb; --muted:#9aa3af; --line:#263041; }} }}
body {{ margin:0; font-family: system-ui, "Segoe UI", Tahoma, sans-serif; background:var(--bg); color:var(--ink); }}
header {{ padding:28px 24px 8px; max-width:1300px; margin:auto; }}
h1 {{ margin:0 0 6px; font-size:26px; }} header p {{ color:var(--muted); margin:0; }}
main {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(520px,1fr)); gap:20px; padding:20px 24px 40px; max-width:1300px; margin:auto; }}
@media (max-width:600px) {{ main {{ grid-template-columns:1fr; padding:16px; }} }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:16px; }}
.card img {{ width:100%; border-radius:8px; display:block; }}
.head {{ display:flex; gap:10px; align-items:center; margin-bottom:10px; flex-wrap:wrap; }}
.kind {{ font-weight:700; }} .sheet {{ color:var(--muted); font-size:13px; }}
.score {{ margin-left:auto; display:flex; align-items:center; gap:6px; font-size:13px; color:var(--muted); }}
progress {{ width:70px; height:8px; accent-color:var(--accent); }}
h3 {{ margin:12px 0 4px; font-size:16px; }} p {{ margin:0 0 8px; color:var(--muted); line-height:1.45; }}
pre {{ background:#0b1220; color:#e5e7eb; padding:12px; border-radius:8px; overflow:auto; font-size:12.5px; }}
summary {{ cursor:pointer; color:var(--accent); font-weight:600; }}
.err {{ padding:30px; background:#fee2e2; color:#991b1b; border-radius:8px; }}
</style></head><body>
<header><h1>Chart suggestions</h1><p>File: {src} · {len(results)} charts · best matches first</p></header>
<main>{''.join(cards)}</main></body></html>"""
    p = out / "report.html"
    p.write_text(page, encoding="utf-8")
    return p
