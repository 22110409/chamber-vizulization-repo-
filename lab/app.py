"""chamberviz Lab: draw every chart type, look at the results side by side, rate them, export a report.

    python lab/app.py            (or run_lab.ps1)

One page:
  1. Settings   designs, size, logo, languages, which charts
  2. Run        the standard test set (lab/cases.py) and/or chart suggestions from your own Excel
  3. Evaluate   click a chart -> large view, automatic checks, score 1-5, verdict, notes
  4. Export     evaluation.md + evaluation.csv + all images in one zip
"""
from __future__ import annotations

import csv
import io
import os
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import gradio as gr  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

import chamberviz as cv  # noqa: E402
from chamberviz import text as cv_text  # noqa: E402
from chamberviz.suggest import profile  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cases import CASES  # noqa: E402
from checks import check  # noqa: E402
from style import (BACKGROUNDS, COLORS, LOGO_MODES, POSITIONS, SETTINGS, SIZES, SettingsError,  # noqa: E402
                   design_colors, style_options)

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_XLSX = ROOT / "examples" / "sample_trade_data.xlsx"
WORK = Path(tempfile.gettempdir()) / "chamberviz_lab"
WORK.mkdir(exist_ok=True)

DESIGNS = cv.list_designs()
LANGS = {"English": "en", "Arabic": "ar"}
LANG_NAMES = {"en": "English", "ar": "Arabic"}
CASE_CHOICES = [(f"{c.name}", c.id) for c in CASES]
VERDICTS = ["good", "needs work", "wrong"]
SCORES = ["1", "2", "3", "4", "5"]
DPI = 130
RENDER = {"concurrency_id": "render", "concurrency_limit": 1}  # matplotlib is not thread-safe

TABLE_HEADERS = ["#", "chart", "design", "language", "from", "time (s)", "automatic checks", "score",
                 "verdict", "notes"]


# ---------------------------------------------------------------- rendering
def styles_for(designs, settings) -> list:
    """[(design name, style kwargs, label, make_design code)] - checked before anything is drawn."""
    st = dict(zip(SETTINGS, settings))
    try:
        return [(name, *style_options(name, st)) for name in designs]
    except SettingsError as exc:
        raise gr.Error(str(exc))


def _error_image(path: Path, message: str):
    fig = plt.figure(figsize=(8, 4.5), dpi=90)
    fig.text(0.5, 0.55, "Render failed", ha="center", fontsize=20, color="#b42318", weight="bold")
    fig.text(0.5, 0.40, message[:160], ha="center", fontsize=10, color="#333", wrap=True)
    fig.savefig(path)
    plt.close(fig)


def draw(make, path: Path) -> dict:
    """Run make() -> Chart, save it, run the automatic checks. Never raises."""
    started = time.perf_counter()
    try:
        chart = make()
        seconds = time.perf_counter() - started
        try:
            warnings = check(chart.fig)
        except Exception as exc:  # the checks must never hide a good chart
            warnings = [f"check failed: {exc}"]
        chart.save(str(path), dpi=DPI)
        chart.close()
        return {"seconds": round(seconds, 2), "checks": warnings, "error": ""}
    except Exception as exc:
        plt.close("all")
        _error_image(path, f"{type(exc).__name__}: {exc}")
        return {"seconds": round(time.perf_counter() - started, 2), "checks": [],
                "error": f"{type(exc).__name__}: {exc}"}


def new_result(results, chart, design, language, origin, image, outcome, code="") -> dict:
    return {"n": len(results) + 1, "chart": chart, "design": design, "language": language,
            "from": origin, "image": str(image), "code": code, "score": "", "verdict": "", "notes": "",
            **outcome}


# ---------------------------------------------------------------- views
def caption(r) -> str:
    marks = ""
    if r["error"]:
        marks = " · ❌ error"
    elif r["checks"]:
        marks = " · ⚠ check"
    if r["score"]:
        marks += f" · ★{r['score']}"
    if r["verdict"]:
        marks += f" · {r['verdict']}"
    return f"#{r['n']} {r['chart']} · {r['design']} · {r['language']} · {r['seconds']:.1f}s{marks}"


def gallery_items(results):
    return [(r["image"], caption(r)) for r in results]


def checks_text(r) -> str:
    if r["error"]:
        return "❌ " + r["error"]
    return "; ".join(r["checks"]) if r["checks"] else "ok"


def table_rows(results):
    return [[r["n"], r["chart"], r["design"], r["language"], r["from"], r["seconds"], checks_text(r),
             r["score"], r["verdict"], r["notes"]] for r in results]


def _avg(scores):
    return f"{sum(scores) / len(scores):.1f}" if scores else "–"


def summary(results) -> str:
    if not results:
        return "_Nothing drawn yet._"
    rated = [r for r in results if r["score"]]
    errors = sum(1 for r in results if r["error"])
    flagged = sum(1 for r in results if r["checks"])
    times = [r["seconds"] for r in results if not r["error"]]
    lines = [f"**{len(results)} charts** · {errors} errors · {flagged} flagged by the checks · "
             f"{len(rated)} rated · average score {_avg([int(r['score']) for r in rated])} · "
             f"average render {_avg(times)} s"]
    for key, title in (("design", "By design"), ("language", "By language")):
        groups = {}
        for r in results:
            groups.setdefault(r[key], []).append(r)
        parts = []
        for name, rs in groups.items():
            scores = [int(r["score"]) for r in rs if r["score"]]
            bad = sum(1 for r in rs if r["verdict"] in ("needs work", "wrong"))
            parts.append(f"{name}: {_avg(scores)} ★ ({len(scores)}/{len(rs)} rated, {bad} need work)")
        lines.append(f"**{title}:** " + " · ".join(parts))
    return "\n\n".join(lines)


def detail(results, index):
    """Everything the evaluation panel shows for one chart."""
    if index is None or not (0 <= index < len(results)):
        return (None, "_Click a chart in the gallery to evaluate it._", None, None, "", gr.update(visible=False),
                None)
    r = results[index]
    info = [f"### #{r['n']} {r['chart']}",
            f"**Design:** {r['design']} · **Language:** {r['language']} · **From:** {r['from']} · "
            f"**Render time:** {r['seconds']:.2f} s",
            f"**Automatic checks:** {checks_text(r)}"]
    code = gr.update(value=r["code"], visible=bool(r["code"]))
    return (r["image"], "\n\n".join(info), r["score"] or None, r["verdict"] or None, r["notes"], code, index)


def refresh(results, selected=None):
    return (gr.update(value=gallery_items(results), selected_index=selected), table_rows(results),
            summary(results))


# ---------------------------------------------------------------- actions
def run_test_set(results, designs, languages, chart_ids, *settings, progress=gr.Progress()):
    if not designs:
        raise gr.Error("Pick at least one design.")
    langs = {LANGS[name] for name in languages}
    picked = [c for c in CASES if c.id in (chart_ids or []) and c.language in langs]
    if not picked:
        raise gr.Error("No charts match: pick at least one chart type and one language.")
    styles = styles_for(designs, settings)
    results = list(results)
    run_dir = Path(tempfile.mkdtemp(prefix="run_", dir=WORK))
    jobs = [(case, s) for s in styles for case in picked]
    for i, (case, (name, style, label, _)) in enumerate(jobs):
        progress(i / len(jobs), desc=f"{case.name} · {label}")
        image = run_dir / f"{len(results) + 1:03d}_{case.id}_{name}.png"
        outcome = draw(lambda: case.draw(style), image)
        results.append(new_result(results, case.name, label, LANG_NAMES[case.language], "test set",
                                  image, outcome))
        yield (results, *refresh(results))
    progress(1.0)


def read_sheets(file):
    if not file:
        return gr.update(choices=[], value=None), ""
    try:
        sheets = cv.read_excel(file)
    except Exception as exc:
        raise gr.Error(f"Could not read the file: {exc}")
    names = list(sheets)
    info = " · ".join(f"**{name}** {len(df)} rows × {len(df.columns)} columns" for name, df in sheets.items())
    return gr.update(choices=["All sheets"] + names, value="All sheets"), info


def use_sample():
    return str(SAMPLE_XLSX), *read_sheets(str(SAMPLE_XLSX))


# ---------------------------------------------------------------- focusing the charts on your data
AUTO = "Auto (best)"
NO_FILTER = "(no filter)"


@lru_cache(maxsize=16)
def _sheet(path: str, sheet: str, mtime: float):
    return cv.read_excel(path, sheet=sheet)


def sheet_df(file, sheet):
    if not file or sheet in (None, "All sheets"):
        return None
    return _sheet(str(file), str(sheet), os.path.getmtime(file))


def sheet_controls(file, sheet):
    """Filter / compare-by / value choices for the chosen sheet (hidden for 'All sheets')."""
    df = sheet_df(file, sheet)
    if df is None:
        hint = "Pick one sheet to filter it or choose the columns." if file else ""
        return (gr.update(visible=False), *(gr.update(choices=[NO_FILTER], value=NO_FILTER) for _ in range(2)),
                *(gr.update(choices=[], value=[]) for _ in range(2)), gr.update(choices=[AUTO], value=AUTO),
                gr.update(choices=[AUTO], value=AUTO), hint)
    cols = profile(df)
    filters = [NO_FILTER] + cv.filter_columns(df)
    by = [AUTO] + [c.name for c in cols if c.kind in ("category", "country", "year", "date") and c.unique > 1]
    values = [AUTO] + [c.name for c in cols if c.kind == "number"]
    return (gr.update(visible=True), gr.update(choices=filters, value=NO_FILTER),
            gr.update(choices=filters, value=NO_FILTER), gr.update(choices=[], value=[]),
            gr.update(choices=[], value=[]), gr.update(choices=by, value=AUTO), gr.update(choices=values, value=AUTO),
            rows_note(file, sheet, NO_FILTER, [], NO_FILTER, []))


def filter_values(file, sheet, column):
    df = sheet_df(file, sheet)
    if df is None or column in (None, NO_FILTER):
        return gr.update(choices=[], value=[], interactive=False)
    return gr.update(choices=cv.filter_choices(df, column), value=[], interactive=True)


def chosen_filters(c1, v1, c2, v2) -> dict:
    out = {}
    for col, vals in ((c1, v1), (c2, v2)):
        if col and col != NO_FILTER and vals:
            out.setdefault(col, [])
            out[col] += [v for v in vals if v not in out[col]]
    return out


def rows_note(file, sheet, c1, v1, c2, v2) -> str:
    df = sheet_df(file, sheet)
    if df is None:
        return ""
    filters = chosen_filters(c1, v1, c2, v2)
    if not filters:
        return f"Using all **{len(df)}** rows. With no choices, chamberviz picks the best column and value itself."
    kept = len(cv.apply_filters(df, filters))
    text = " · ".join(f"{c}: {', '.join(map(str, v))}" for c, v in filters.items())
    warn = " ⚠ no rows left: loosen the filter." if kept == 0 else ""
    return f"Using **{kept}** of {len(df)} rows · {text}{warn}"


def suggestion_code(idea, name, design_code) -> str:
    if not design_code:
        return idea.code(design=name)
    head, _, rest = idea.code(design="my_colours").partition("\n")
    return f"{head}\n{design_code}\n{rest}"


def run_suggestions(results, file, sheet, top, c1, v1, c2, v2, by, value, designs, *settings,
                    progress=gr.Progress()):
    if not file:
        raise gr.Error("Upload an Excel or CSV file first (or click 'Use the sample file').")
    if not designs:
        raise gr.Error("Pick at least one design.")
    styles = styles_for(designs, settings)
    one_sheet = sheet not in (None, "All sheets")
    filters = chosen_filters(c1, v1, c2, v2) if one_sheet else {}
    progress(0, desc="Reading the data and choosing charts")
    try:
        ideas = cv.suggest(file, sheet=sheet if one_sheet else None, top=int(top), verbose=False,
                           filters=filters or None,
                           by=by if one_sheet and by not in (None, AUTO) else None,
                           value=value if one_sheet and value not in (None, AUTO) else None)
    except Exception as exc:
        raise gr.Error(f"suggest() failed: {type(exc).__name__}: {exc}")
    if not ideas:
        if filters:
            raise gr.Error("No chart suggestions for these rows: the filter leaves too little data. "
                           "Pick more values or remove a filter.")
        raise gr.Error("No chart suggestions: the sheet needs at least one numeric column.")
    results = list(results)
    run_dir = Path(tempfile.mkdtemp(prefix="data_", dir=WORK))
    jobs = [(idea, s) for s in styles for idea in ideas]
    for i, (idea, (name, style, label, design_code)) in enumerate(jobs):
        progress(i / len(jobs), desc=f"{idea.name} · {label}")
        image = run_dir / f"{len(results) + 1:03d}_{idea.chart}_{name}.png"
        outcome = draw(lambda: idea.render(**style), image)
        language = "Arabic" if cv_text.has_arabic(idea.title) else "English"
        origin = f"your data · {idea.sheet} · score {idea.score:.0f}"
        results.append(new_result(results, f"{idea.name}: {idea.title}", label, language, origin, image,
                                  outcome, code=suggestion_code(idea, name, design_code)))
        yield (results, *refresh(results))
    progress(1.0)


def save_rating(results, index, score, verdict, notes, advance):
    if index is None or not (0 <= index < len(results)):
        raise gr.Error("Click a chart in the gallery first.")
    results = list(results)
    results[index] = {**results[index], "score": score or "", "verdict": verdict or "", "notes": notes or ""}
    target = min(index + 1, len(results) - 1) if advance else index
    return (results, *refresh(results, target), *detail(results, target))


def clear_all():
    return ([], *refresh([]), *detail([], None))


def export(results):
    if not results:
        raise gr.Error("Nothing to export yet: run the test set first.")
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    out = WORK / f"chamberviz_evaluation_{stamp}.zip"
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(TABLE_HEADERS + ["image"])
    for r, row in zip(results, table_rows(results)):
        writer.writerow(row + [f"images/{Path(r['image']).name}"])

    md = [f"# chamberviz evaluation, {datetime.now():%Y-%m-%d %H:%M}", "",
          f"chamberviz {cv.__version__} · matplotlib {matplotlib.__version__} · "
          f"Arabic: {'matplotlib native' if cv_text.NATIVE_ARABIC else 'reshaped'}", "",
          "## Summary", "", summary(results), "",
          "## Charts", "", "| " + " | ".join(TABLE_HEADERS) + " |", "|" + "---|" * len(TABLE_HEADERS)]
    for row in table_rows(results):
        md.append("| " + " | ".join(str(v).replace("|", "/").replace("\n", " ") for v in row) + " |")
    problems = [r for r in results if r["verdict"] in ("needs work", "wrong") or r["error"]]
    if problems:
        md += ["", "## To fix", ""]
        for r in problems:
            what = r["notes"] or checks_text(r)
            md.append(f"- **#{r['n']} {r['chart']}** ({r['design']}, {r['language']}): {what} "
                      f"![](images/{Path(r['image']).name})")

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("evaluation.md", "\n".join(md) + "\n")
        z.writestr("evaluation.csv", "﻿" + buf.getvalue())  # BOM so Excel reads Arabic
        for r in results:
            z.write(r["image"], f"images/{Path(r['image']).name}")
    return str(out)


# ---------------------------------------------------------------- page
CSS = """
.env-line {opacity: .75; font-size: .9em}
#big-chart img {object-fit: contain}
"""


def build() -> gr.Blocks:
    arabic_mode = "matplotlib native" if cv_text.NATIVE_ARABIC else "reshaped by chamberviz"
    with gr.Blocks(title="chamberviz Lab") as demo:
        results = gr.State([])
        selected = gr.State(None)

        gr.Markdown("# chamberviz Lab\nDraw the charts, look at them, rate them, export the evaluation.")
        gr.Markdown(f"chamberviz {cv.__version__} · matplotlib {matplotlib.__version__} · "
                    f"Arabic text: {arabic_mode} · {len(CASES)} test charts", elem_classes="env-line")

        # 1. settings -----------------------------------------------------
        gr.Markdown("## 1. Settings")
        first_colors, first_series = design_colors(DESIGNS[0])
        with gr.Row():
            designs = gr.Dropdown(DESIGNS, value=[DESIGNS[0]], multiselect=True, label="Designs",
                                  info="Pick several to compare the same chart across designs")
            size = gr.Dropdown(list(SIZES), value="Design default", label="Figure size")
            languages = gr.CheckboxGroup(list(LANGS), value=list(LANGS), label="Languages")

        gr.Markdown("### Logos")
        with gr.Row(equal_height=False):
            logo_mode = gr.Radio(LOGO_MODES, value="One logo", label="How many logos?")
            with gr.Column():
                logo1 = gr.Image(type="filepath", image_mode="RGBA", format="png", label="Logo 1 (PNG or JPG, empty = demo logo)", height=130,
                                 sources=["upload"])
                pos1 = gr.Dropdown(POSITIONS, value="top-right", label="Logo 1 position")
            with gr.Column(visible=False) as logo2_box:
                logo2 = gr.Image(type="filepath", image_mode="RGBA", format="png", label="Logo 2 (PNG or JPG, empty = demo logo)", height=130,
                                 sources=["upload"])
                pos2 = gr.Dropdown(POSITIONS, value="top-left", label="Logo 2 position")

        gr.Markdown("### Background")
        with gr.Row(equal_height=False):
            bg_mode = gr.Radio(BACKGROUNDS, value=BACKGROUNDS[0], label="Behind the chart")
            with gr.Column(visible=False) as photo_box:
                bg_photo = gr.Image(type="filepath", label="Background photo (JPG or PNG)", height=130,
                                    sources=["upload"])
                bg_opacity = gr.Slider(0.05, 1.0, value=0.35, step=0.05, label="Photo strength",
                                       info="Low = faint photo, the chart stays easy to read")
                keep_map = gr.Checkbox(False, label="Also draw the world map over the photo")

        gr.Markdown("### Colours")
        custom = gr.Checkbox(False, label="Use my own colours",
                             info="The pickers start from the first chosen design. Only the colours you "
                                  "change are applied, to every chosen design.")
        color_base = gr.State(DESIGNS[0])
        with gr.Group(visible=False) as colors_box:
            pickers = {}
            keys = list(COLORS)
            for row in (keys[:4], keys[4:]):
                with gr.Row():
                    for key in row:
                        pickers[key] = gr.ColorPicker(first_colors[key], label=COLORS[key])
            series = gr.Textbox(first_series, label="Series colours (lines, grouped bars, donut slices), "
                                                    "in order, separated by commas")
            reset_colors = gr.Button("Reset to the design's colours", size="sm")

        # 2. run ----------------------------------------------------------
        gr.Markdown("## 2. Draw")
        with gr.Row(equal_height=False):
            with gr.Column(scale=3):
                gr.Markdown("**The test set**: every chart type with sample trade data.")
                chart_ids = gr.CheckboxGroup(CASE_CHOICES, value=[c.id for c in CASES], label="Charts")
                with gr.Row():
                    select_all = gr.Button("Select all", size="sm")
                    select_none = gr.Button("Select none", size="sm")
                run_btn = gr.Button("▶ Run the test set", variant="primary")
            with gr.Column(scale=2):
                gr.Markdown("**Your own data**: chamberviz reads the file and suggests charts.")
                data_file = gr.File(label="Excel or CSV", file_types=[".xlsx", ".xls", ".csv"],
                                    type="filepath")
                sample_btn = gr.Button("Use the sample file", size="sm")
                sheet_info = gr.Markdown()
                with gr.Row():
                    sheet = gr.Dropdown([], label="Sheet", interactive=True)
                    top = gr.Slider(1, 10, value=3, step=1, label="Suggestions per sheet")
                focus_hint = gr.Markdown()
                with gr.Group(visible=False) as focus_box:
                    gr.Markdown("&nbsp;**Focus the charts** (optional)")
                    with gr.Row():
                        f1_col = gr.Dropdown([NO_FILTER], value=NO_FILTER, label="Filter 1: only rows where")
                        f1_vals = gr.Dropdown([], value=[], multiselect=True, label="is one of",
                                              interactive=False)
                    with gr.Row():
                        f2_col = gr.Dropdown([NO_FILTER], value=NO_FILTER, label="Filter 2: and where")
                        f2_vals = gr.Dropdown([], value=[], multiselect=True, label="is one of",
                                              interactive=False)
                    with gr.Row():
                        by_col = gr.Dropdown([AUTO], value=AUTO, label="Compare by",
                                             info="the bars / slices / lines")
                        value_col = gr.Dropdown([AUTO], value=AUTO, label="Value", info="the number to show")
                suggest_btn = gr.Button("▶ Draw the suggestions", variant="primary")

        # 3. evaluate -----------------------------------------------------
        gr.Markdown("## 3. Evaluate\nClick a chart to see it large and rate it.")
        overview = gr.Markdown(summary([]))
        gallery = gr.Gallery(label="Charts", columns=3, height=620, object_fit="contain",
                             allow_preview=False)
        with gr.Row(equal_height=False):
            with gr.Column(scale=3):
                big = gr.Image(label="Selected chart", interactive=False, elem_id="big-chart", height=560)
            with gr.Column(scale=2):
                info = gr.Markdown("_Click a chart in the gallery to evaluate it._")
                score = gr.Radio(SCORES, label="Score (1 = bad, 5 = ready to publish)")
                verdict = gr.Radio(VERDICTS, label="Verdict")
                notes = gr.Textbox(label="Notes (what is wrong, what to change)", lines=3)
                with gr.Row():
                    save_btn = gr.Button("Save")
                    next_btn = gr.Button("Save and next", variant="primary")
                code = gr.Code(label="Code for this chart", language="python", visible=False)
        table = gr.Dataframe(headers=TABLE_HEADERS, value=[], interactive=False, wrap=True,
                             label="All results", max_height=420,
                             column_widths=["4%", "20%", "9%", "7%", "13%", "6%", "17%", "5%", "8%", "11%"])

        # 4. export -------------------------------------------------------
        gr.Markdown("## 4. Export")
        with gr.Row():
            export_btn = gr.Button("⬇ Export the evaluation (report + table + images)", variant="primary")
            clear_btn = gr.Button("Clear all results", variant="stop")
        report = gr.File(label="Evaluation zip", interactive=False)

        # wiring ----------------------------------------------------------
        views = [gallery, table, overview]
        panel = [big, info, score, verdict, notes, code, selected]
        by_name = {"size": size, "logo_mode": logo_mode, "logo1": logo1, "pos1": pos1, "logo2": logo2,
                   "pos2": pos2, "bg_mode": bg_mode, "bg_photo": bg_photo, "bg_opacity": bg_opacity,
                   "keep_map": keep_map, "custom": custom, "color_base": color_base, "series": series,
                   **pickers}
        settings = [by_name[name] for name in SETTINGS]
        color_outputs = [color_base, *pickers.values(), series]

        def load_colors(name):
            colors, series_text = design_colors(name)
            return [name, *colors.values(), series_text]

        def follow_design(chosen, base):
            # the pickers follow the first chosen design; adding a second design keeps your edits
            if not chosen or chosen[0] == base:
                return [gr.update() for _ in color_outputs]
            return load_colors(chosen[0])

        logo_mode.change(lambda m: (gr.update(visible=m != "No logo"), gr.update(visible=m == "Two logos")),
                         logo_mode, [logo1, logo2_box])
        logo_mode.change(lambda m: gr.update(visible=m != "No logo"), logo_mode, pos1)
        bg_mode.change(lambda m: gr.update(visible=m == "My photo"), bg_mode, photo_box)
        custom.change(lambda on: gr.update(visible=on), custom, colors_box)
        designs.change(follow_design, [designs, color_base], color_outputs)
        reset_colors.click(lambda chosen: load_colors((chosen or DESIGNS)[0]), designs, color_outputs)

        select_all.click(lambda: [c.id for c in CASES], None, chart_ids)
        select_none.click(lambda: [], None, chart_ids)
        run_btn.click(run_test_set, [results, designs, languages, chart_ids, *settings], [results, *views],
                      **RENDER)
        data_file.change(read_sheets, data_file, [sheet, sheet_info])
        sample_btn.click(use_sample, None, [data_file, sheet, sheet_info])
        focus_outputs = [focus_box, f1_col, f2_col, f1_vals, f2_vals, by_col, value_col, focus_hint]
        sheet.change(sheet_controls, [data_file, sheet], focus_outputs)
        f1_col.change(filter_values, [data_file, sheet, f1_col], f1_vals)
        f2_col.change(filter_values, [data_file, sheet, f2_col], f2_vals)
        note_inputs = [data_file, sheet, f1_col, f1_vals, f2_col, f2_vals]
        for control in (f1_col, f1_vals, f2_col, f2_vals):
            control.change(rows_note, note_inputs, focus_hint)
        suggest_btn.click(run_suggestions, [results, data_file, sheet, top, f1_col, f1_vals, f2_col, f2_vals,
                                            by_col, value_col, designs, *settings],
                          [results, *views], **RENDER)

        def on_select(res, evt: gr.SelectData):
            return detail(res, evt.index)

        gallery.select(on_select, results, panel)
        save_btn.click(lambda r, i, s, v, n: save_rating(r, i, s, v, n, False),
                       [results, selected, score, verdict, notes], [results, *views, *panel])
        next_btn.click(lambda r, i, s, v, n: save_rating(r, i, s, v, n, True),
                       [results, selected, score, verdict, notes], [results, *views, *panel])
        export_btn.click(export, results, report)
        clear_btn.click(clear_all, None, [results, *views, *panel])
    return demo


def free_port(preferred: int, tries: int = 20) -> int:
    """The preferred port, or the next free one (e.g. when a Lab is already open in another window)."""
    import socket
    for port in range(preferred, preferred + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise OSError(f"No free port between {preferred} and {preferred + tries - 1}.")


if __name__ == "__main__":
    wanted = int(os.environ.get("CHAMBERVIZ_LAB_PORT", "7863"))
    port = free_port(wanted)
    if port != wanted:
        print(f"Port {wanted} is busy (a Lab may already be open at http://127.0.0.1:{wanted}); using {port}.")
    print(f"chamberviz Lab: http://127.0.0.1:{port}")
    build().launch(server_name="127.0.0.1", server_port=port, inbrowser="--no-browser" not in sys.argv,
                   css=CSS, allowed_paths=[str(WORK)])
