"""Command line:

  python -m chamberviz suggest data.xlsx            list chart ideas for every sheet
  python -m chamberviz auto data.xlsx -o charts     draw the best ideas + report.html
  python -m chamberviz designs                      preview every design
  python -m chamberviz icons truck                  find icons by name
  python -m chamberviz flags                        sheet of all flags
  python -m chamberviz logo path/to/logo.png        save your logo as the default
  python -m chamberviz app                          open the upload app in the browser
  python -m chamberviz dashboard                    open Chamber Studio (Power BI-style dashboard)
"""
import argparse
import subprocess
import sys
from pathlib import Path


def main(argv=None):
    import chamberviz as cv
    ap = argparse.ArgumentParser(prog="chamberviz", description="Branded charts and Excel chart suggestions")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("suggest", help="list chart ideas for an Excel/CSV file")
    p.add_argument("file")
    p.add_argument("--sheet")
    p.add_argument("--top", type=int, default=8)
    p = sub.add_parser("auto", help="draw the best charts and write report.html")
    p.add_argument("file")
    p.add_argument("-o", "--out", default="charts")
    p.add_argument("--sheet")
    p.add_argument("--top", type=int, default=4)
    p.add_argument("--design")
    p.add_argument("--logo-alignment", default=None)
    p.add_argument("--no-logo", action="store_true")
    p.add_argument("--source")
    p = sub.add_parser("designs", help="preview all designs")
    p.add_argument("-o", "--out", default="designs_preview.png")
    p = sub.add_parser("icons", help="search icons")
    p.add_argument("query", nargs="?", default="")
    p.add_argument("--filled", action="store_true")
    p = sub.add_parser("flags", help="sheet with every flag")
    p.add_argument("--style", default="round", choices=["round", "rect"])
    p.add_argument("--arabic", action="store_true")
    p = sub.add_parser("logo", help="save your logo as the default for every chart")
    p.add_argument("path")
    sub.add_parser("app", help="open the Excel upload app (needs: pip install streamlit)")
    p = sub.add_parser("dashboard", help="open Chamber Studio, the dashboard app (needs streamlit + plotly)")
    p.add_argument("--port", type=int, default=8501)
    p.add_argument("--headless", action="store_true", help="do not open a browser")
    a = ap.parse_args(argv)

    if a.cmd == "suggest":
        cv.suggest(a.file, a.sheet, top=a.top)
    elif a.cmd == "auto":
        style = {}
        if a.no_logo:
            style["logo"] = None
        if a.logo_alignment:
            style["logo_alignment"] = a.logo_alignment
        if a.source:
            style["source"] = a.source
        cv.auto(a.file, out_dir=a.out, sheet=a.sheet, top=a.top, design=a.design, **style)
    elif a.cmd == "designs":
        print("saved", cv.preview_designs(a.out))
    elif a.cmd == "icons":
        v = "filled" if a.filled else "outline"
        names = cv.icon_sheet(a.query, v)
        print(f"{len(names)} icons (sheet saved as icons_{a.query or 'all'}.png):")
        print(", ".join(names))
    elif a.cmd == "flags":
        print("saved", cv.flag_sheet(style=a.style, language="ar" if a.arabic else "en"))
    elif a.cmd == "logo":
        print("default logo saved:", cv.set_default_logo(a.path))
    elif a.cmd == "app":
        app = Path(__file__).with_name("app.py")
        subprocess.run([sys.executable, "-m", "streamlit", "run", str(app)])
    elif a.cmd == "dashboard":
        studio = Path(__file__).resolve().parents[1] / "chamberstudio" / "app.py"
        if not studio.exists():
            raise SystemExit("Chamber Studio is not installed next to chamberviz (chamberstudio/app.py).")
        cmd = [sys.executable, "-m", "streamlit", "run", str(studio), "--server.port", str(a.port),
               "--server.address", "127.0.0.1", "--client.toolbarMode", "minimal",
               "--theme.primaryColor", "#b8862e",
               "--browser.gatherUsageStats", "false"]
        if a.headless:
            cmd += ["--server.headless", "true"]
        subprocess.run(cmd)


if __name__ == "__main__":
    main()
