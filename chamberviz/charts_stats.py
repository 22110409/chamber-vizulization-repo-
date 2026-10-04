"""Pie/donut, line/area, histogram, box plot, scatter/bubble and heatmap."""
from __future__ import annotations

import numpy as np
from matplotlib.colors import LinearSegmentedColormap, to_rgba
from matplotlib.patches import Ellipse, Wedge
from matplotlib.ticker import MaxNLocator

from . import config
from ._draw import (bar, draw_icon, get_flag, place_image, px_scale, resolve_flags,
                    resolve_icons, rgba, style_axes, text_color_on, to_fig, xy)
from .canvas import Frame
from .charts_bar import VALUE_OPTS, _nice_limits, _text_width_in, _tick_fmt, _vfmt, draw_legend
from .text import fmt, font, has_arabic, label, shape


def _series_colors(d, n, colors=None):
    base = list(colors) if colors else list(d.series)
    return [base[i % len(base)] for i in range(n)]


# ======================================================================
def pieplot(data=None, values=None, *, x=None, y=None, donut=True, colors=None,
            max_slices=8, other_label=None, center_text="auto", center_label=None,
            show_percent=True, show_values=True, flags="auto", icons=None, flag_style=None,
            sort="desc", start_angle=90, **kw):
    """Pie or donut chart with a legend that shows value and share.

    pieplot(["Industry", "Trade", "Services"], [45, 30, 25], donut=True)
    """
    opts = {k: kw.pop(k) for k in list(kw) if k in VALUE_OPTS}
    fr = Frame("pieplot", **kw)
    d, s = fr.design, fr.s
    labels, vals = xy(data, values, x, y, "pieplot")
    fl = resolve_flags(labels, flags)
    ic = resolve_icons(labels, icons)
    idx = list(range(len(vals)))
    if sort:
        idx.sort(key=lambda i: -vals[i])
    labels = [labels[i] for i in idx]
    vals = [vals[i] for i in idx]
    fl = [fl[i] for i in idx] if fl else None
    ic = [ic[i] for i in idx] if ic else None
    arabic = any(has_arabic(l) for l in labels)
    if len(vals) > max_slices:
        rest = sum(vals[max_slices - 1:])
        labels = labels[:max_slices - 1] + [other_label or ("أخرى" if arabic else "Other")]
        vals = vals[:max_slices - 1] + [rest]
        fl = fl[:max_slices - 1] + [None] if fl else None
        ic = ic[:max_slices - 1] + ["dots"] if ic else None
    total = sum(vals)
    vf = _vfmt(opts, vals)
    cols = _series_colors(d, len(vals), colors)
    cols = [c[1] if isinstance(c, (tuple, list)) else c for c in cols]
    # layout: pie on one side, legend on the other
    rect_all = fr.plot_rect(left=0.5, right=0.5, bottom=0.2, top=0.2)
    total_w = rect_all[2] * fr.W
    ph = rect_all[3] * fr.H
    side = min(ph, total_w * 0.5)
    pie_left = rect_all[0] * fr.W + (total_w * (0.55 if arabic else 0.02))
    if arabic:
        pie_left = rect_all[0] * fr.W + total_w - side - 0.1 * s
    else:
        pie_left = rect_all[0] * fr.W + 0.1 * s
    pb = rect_all[1] * fr.H + (ph - side) / 2
    ax = fr.fig.add_axes([pie_left / fr.W, pb / fr.H, side / fr.W, side / fr.H])
    ax.set_xlim(-1.08, 1.08)
    ax.set_ylim(-1.08, 1.08)
    ax.set_aspect("equal")
    ax.axis("off")
    ang = start_angle
    width = 0.38 if donut else 1.0
    for i, v in enumerate(vals):
        sweep = 360 * v / total if total else 0
        mid = np.deg2rad(ang - sweep / 2)
        off = 0.04 if i == 0 else 0.0
        cx, cy = off * np.cos(mid), off * np.sin(mid)
        ax.add_patch(Wedge((cx, cy), 1.0, ang - sweep, ang, width=width, facecolor=cols[i],
                           edgecolor=d.surface, linewidth=2.2 * s))
        pct = v / total * 100 if total else 0
        if show_percent and pct >= 4:
            r = 1 - width / 2 if donut else 0.64
            ax.text(cx + r * np.cos(mid), cy + r * np.sin(mid), f"{pct:.0f}%", ha="center",
                    va="center", fontsize=fr.fs(13 if pct >= 8 else 10.5),
                    fontproperties=font("sans", "bold"), color=text_color_on(cols[i]))
        ang -= sweep
    if donut and center_text is not None:
        ct = vf(total) if center_text == "auto" else str(center_text)
        ax.text(0, 0.08, shape(ct), ha="center", va="center", fontsize=fr.fs(26),
                fontproperties=font("sans", "heavy", ct), color=d.title_color)
        cl = center_label if center_label is not None else ("الإجمالي" if arabic else "Total")
        ax.text(0, -0.14, shape(cl), ha="center", va="center", fontsize=fr.fs(13),
                fontproperties=font("sans", "regular", cl), color=d.muted_color)
    # legend
    n = len(vals)
    row = min(0.62 * s, ph / max(n, 1))
    fsz = fr.fs(14 if row > 0.5 * s else 12)
    leg_x0 = (pie_left + side + 0.5 * s) if not arabic else (rect_all[0] * fr.W + 0.3 * s)
    leg_x1 = (rect_all[0] + rect_all[2]) * fr.W - 0.2 * s if not arabic else pie_left - 0.5 * s
    top = rect_all[1] * fr.H + ph / 2 + row * n / 2
    fl_style = flag_style or config.DEFAULTS["flag_style"]
    for i in range(n):
        yc = (top - row * (i + 0.5)) / fr.H
        pct = vals[i] / total * 100 if total else 0
        num = (vf(vals[i]) if show_values else "") + (f"   {pct:.1f}%" if show_percent else "")
        sw = 0.2 * s
        if not arabic:
            x = leg_x0
            fr.fig.add_artist(Ellipse(((x + sw / 2) / fr.W, yc), sw / fr.W, sw / fr.H,
                                      facecolor=cols[i], transform=fr.fig.transFigure))
            x += sw + 0.15 * s
            img = get_flag(fl[i], fl_style) if fl else None
            if img is not None:
                place_image(ax, img, (x + 0.15 * s) / fr.W, yc, 0.3 * s)
                x += 0.42 * s
            elif ic and ic[i]:
                from .assets_lookup import icon_char
                from .text import icon_font
                try:
                    fr.fig.text(x / fr.W, yc, icon_char(ic[i]), fontproperties=icon_font(),
                                fontsize=fsz * 1.3, color=d.icon_color, va="center")
                    x += 0.4 * s
                except KeyError:
                    pass
            fr.fig.text(x / fr.W, yc, label(labels[i], 34), va="center", ha="left", fontsize=fsz,
                        fontproperties=font("sans", "regular", labels[i]), color=d.text_color)
            fr.fig.text(leg_x1 / fr.W, yc, num, va="center", ha="right", fontsize=fsz,
                        fontproperties=font("sans", "bold"), color=d.value_color)
        else:
            x = leg_x1
            fr.fig.add_artist(Ellipse(((x - sw / 2) / fr.W, yc), sw / fr.W, sw / fr.H,
                                      facecolor=cols[i], transform=fr.fig.transFigure))
            x -= sw + 0.15 * s
            img = get_flag(fl[i], fl_style) if fl else None
            if img is not None:
                place_image(ax, img, (x - 0.15 * s) / fr.W, yc, 0.3 * s)
                x -= 0.42 * s
            fr.fig.text(x / fr.W, yc, label(labels[i], 34), va="center", ha="right", fontsize=fsz,
                        fontproperties=font("sans", "bold", labels[i]), color=d.text_color)
            fr.fig.text(leg_x0 / fr.W, yc, num, va="center", ha="left", fontsize=fsz,
                        fontproperties=font("sans", "bold"), color=d.value_color)
        if i < n - 1:
            ly = yc - row / 2 / fr.H
            fr.fig.add_artist(__import__("matplotlib").lines.Line2D(
                [leg_x0 / fr.W, leg_x1 / fr.W], [ly, ly], color=d.grid_color, alpha=d.grid_alpha,
                linewidth=0.8, transform=fr.fig.transFigure))
    return fr.finish()


# ======================================================================
def _x_labels(xs):
    import pandas as pd
    out = []
    try:
        dt = pd.to_datetime(pd.Series(xs), errors="raise") if not all(
            isinstance(v, (int, np.integer, float)) for v in xs) else None
    except Exception:
        dt = None
    if dt is not None:
        monthly = len(set(dt.dt.year)) < len(dt)
        return [t.strftime("%b %Y") if monthly else str(t.year) for t in dt]
    for v in xs:
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        out.append(str(v))
    return out


def lineplot(data=None, series=None, *, x=None, y=None, colors=None, area=None,
             markers=True, value_labels="auto", show_change=False, ylabel=None,
             legend="auto", end_labels="auto", smooth=False, highlight_last=True,
             ymin=None, ymax=None, **kw):
    """Line / area chart over time.

    lineplot([2021, 2022, 2023], [10, 12, 15])                     # one series
    lineplot(years, {"Imports": [...], "Exports": [...]})          # several series
    lineplot(df, x="Year", y=["Imports", "Exports"])              # from a DataFrame
    """
    opts = {k: kw.pop(k) for k in list(kw) if k in VALUE_OPTS}
    fr = Frame("lineplot", **kw)
    d, s = fr.design, fr.s
    import pandas as pd
    if isinstance(data, pd.DataFrame):
        from ._draw import series_input
        xs, ser = series_input(data, x, y)
    elif isinstance(series, dict):
        xs, ser = list(data), {str(k): [float(v) for v in vv] for k, vv in series.items()}
    else:
        xs, vals = xy(data, series, x, y, "lineplot")
        ser = {ylabel or "": vals}
    names = list(ser)
    k, n = len(names), len(xs)
    area = (k == 1) if area is None else area
    allv = [v for nm in names for v in ser[nm] if v == v]
    vf = _vfmt(opts, allv)
    cols = [d.accent] if k == 1 and not colors else _series_colors(d, k, colors)
    cols = [c[1] if isinstance(c, (tuple, list)) else c for c in cols]
    show_end = (k > 1 and k <= 5) if end_labels == "auto" else end_labels
    right_in = 0.6
    if show_end:
        right_in = max(_text_width_in(fr, shape(nm), fr.fs(12)) for nm in names) / s + 1.3
    show_leg = (k > 1) if legend == "auto" else legend
    rect = fr.plot_rect(left=1.0 + (0.45 if ylabel and k > 1 else 0), right=right_in, bottom=0.75,
                        top=0.7 if show_leg else 0.35)
    ax = fr.fig.add_axes(rect)
    pos = np.arange(n)
    ax.set_xlim(-0.3 if n > 1 else -1, n - 0.7 if n > 1 else 1)
    lo = min(allv)
    hi = max(allv)
    span = (hi - lo) or abs(hi) or 1
    ybot = ymin if ymin is not None else (0 if lo >= 0 and lo < span * 1.2 else lo - span * 0.15)
    ytop = ymax if ymax is not None else hi + span * 0.18
    ax.set_ylim(ybot, ytop)
    style_axes(ax, fr, grid="y")
    ax.yaxis.set_major_formatter(_tick_fmt(allv))
    ax.yaxis.set_major_locator(MaxNLocator(6))
    labs = _x_labels(xs)
    step = max(1, int(np.ceil(n / 12)))
    ax.set_xticks(pos[::step])
    ax.set_xticklabels([shape(l) for l in labs[::step]], fontsize=fr.fs(12))
    if ylabel and k > 1:
        ax.set_ylabel(shape(ylabel), fontproperties=font("sans", "bold", ylabel),
                      fontsize=fr.fs(14), color=d.text_color, labelpad=10 * s)
    ends = []
    for j, nm in enumerate(names):
        ys = np.array(ser[nm], dtype=float)
        px, py = pos, ys
        if smooth and n > 3:
            fine = np.linspace(0, n - 1, n * 12)
            py = np.interp(fine, pos, ys)
            kern = np.ones(9) / 9
            py = np.convolve(np.pad(py, 4, mode="edge"), kern, mode="valid")
            px = fine
        c = cols[j]
        lw = (3.2 if j == 0 else 2.4) * s
        ax.plot(px, py, color=c, linewidth=lw, zorder=4 + (k - j), solid_capstyle="round")
        if area and (j == 0):
            verts_top = ytop
            grad = np.linspace(0, 1, 256).reshape(-1, 1)
            cmap = LinearSegmentedColormap.from_list("a", [rgba(c, 0.0), rgba(c, 0.38)])
            im = ax.imshow(grad, aspect="auto", origin="lower", cmap=cmap,
                           extent=[px[0], px[-1], ybot, max(py)], zorder=2)
            poly = ax.fill_between(px, py, ybot, color="none")
            im.set_clip_path(poly.get_paths()[0], transform=ax.transData)
        if markers and n <= 40:
            ax.scatter(pos, ys, s=(55 if n <= 15 else 25) * s ** 2, color=c, edgecolor=d.surface,
                       linewidth=1.8 * s, zorder=6 + (k - j))
        vl = ("all" if (k == 1 and n <= 14) else "last") if value_labels == "auto" else value_labels
        pts = []
        if vl == "all":
            pts = list(range(n))
        elif vl == "last":
            pts = [n - 1]
        elif vl == "minmax":
            pts = sorted({int(np.nanargmin(ys)), int(np.nanargmax(ys)), n - 1})
        for i in pts:
            last = i == n - 1
            ax.annotate(vf(ys[i]), (pos[i], ys[i]), xytext=(0, 11 * s), textcoords="offset points",
                        ha="center", va="bottom", fontsize=fr.fs(13 if last and highlight_last else 11),
                        fontproperties=font("sans", "bold"),
                        color=(d.highlight_value_color if (last and highlight_last and k == 1) else d.value_color),
                        zorder=9, annotation_clip=False)
        if highlight_last and n:
            ax.scatter([pos[-1]], [ys[-1]], s=160 * s ** 2, color=rgba(c, 0.25), zorder=5, linewidth=0)
        if show_end:
            txt = nm
            if show_change and ys[0]:
                txt += f"  {((ys[-1] - ys[0]) / abs(ys[0]) * 100):+.1f}%"
            ends.append((ys[-1], txt, nm, c))
    # end labels: pushed apart so lines that finish close together stay readable
    if ends:
        gap = fr.fs(12.5) * 1.45
        to_pt = lambda y: ax.transData.transform((pos[-1], y))[1] * 72 / fr.fig.dpi  # noqa: E731
        order = sorted(range(len(ends)), key=lambda i: to_pt(ends[i][0]))
        placed = [to_pt(ends[i][0]) for i in order]
        for i in range(1, len(placed)):
            placed[i] = max(placed[i], placed[i - 1] + gap)
        shift = max(0.0, placed[-1] - to_pt(ax.get_ylim()[1]))   # keep the top one inside the axes
        for i, want in zip(order, placed):
            y, txt, nm, c = ends[i]
            ax.annotate(shape(txt), (pos[-1], y), xytext=(14 * s, want - shift - to_pt(y)),
                        textcoords="offset points", va="center", ha="left", fontsize=fr.fs(12.5),
                        fontproperties=font("sans", "bold", nm), color=c, annotation_clip=False)
    if show_change and k == 1 and n > 1 and ser[names[0]][0]:
        ys = ser[names[0]]
        ch = (ys[-1] - ys[0]) / abs(ys[0]) * 100
        ax.text(0.0, 1.02, f"{ch:+.1f}%  {labs[0]} → {labs[-1]}", transform=ax.transAxes,
                ha="left", va="bottom", fontsize=fr.fs(14), fontproperties=font("sans", "bold"),
                color=d.positive if ch >= 0 else d.negative)
    if show_leg:
        draw_legend(fr, ax, names, cols, y_axes=1.0 + 0.35 * s / (rect[3] * fr.H), marker="line")
    return fr.finish()


def areaplot(*args, **kw):
    """Same as lineplot(..., area=True)."""
    kw.setdefault("area", True)
    return lineplot(*args, **kw)


# ======================================================================
def histplot(values, *, bins="auto", color=None, show_mean=True, show_median=True,
             xlabel=None, ylabel=None, **kw):
    """Histogram of one numeric column (distribution of values)."""
    opts = {k: kw.pop(k) for k in list(kw) if k in VALUE_OPTS}
    fr = Frame("histplot", **kw)
    d, s = fr.design, fr.s
    import pandas as pd
    v = np.asarray(pd.to_numeric(pd.Series(list(values)), errors="coerce").dropna(), dtype=float)
    if isinstance(bins, str):
        edges = np.histogram_bin_edges(v, bins=bins)
        if len(edges) - 1 > 40:
            edges = np.histogram_bin_edges(v, bins=40)
        if len(edges) - 1 < 8:
            edges = np.histogram_bin_edges(v, bins=10)
    else:
        edges = np.histogram_bin_edges(v, bins=bins)
    counts, edges = np.histogram(v, bins=edges)
    rect = fr.plot_rect(left=1.0 + (0.4 if ylabel else 0), right=0.5, bottom=0.8 + (0.35 if xlabel else 0), top=0.55)
    ax = fr.fig.add_axes(rect)
    ax.set_xlim(edges[0] - (edges[1] - edges[0]) * 0.3, edges[-1] + (edges[1] - edges[0]) * 0.3)
    ax.set_ylim(0, max(counts) * 1.18 if len(counts) else 1)
    style_axes(ax, fr, grid="y")
    ax.xaxis.set_major_formatter(_tick_fmt(list(v)))
    grad = (color, color) if color else d.bar
    w = edges[1] - edges[0]
    for c, e in zip(counts, edges[:-1]):
        if c:
            bar(ax, e + w / 2, c, w * 0.9, grad, cap=d.bar_cap or None, cap_width=1.5 * s, outline=False)
    vf = _vfmt(opts, list(v))
    marks = []
    if show_mean:
        marks.append(("Mean", float(np.mean(v)), d.accent, "--"))
    if show_median:
        marks.append(("Median", float(np.median(v)), d.text_color, ":"))
    marks.sort(key=lambda m: m[1])
    for j, (nm, val, c, ls) in enumerate(marks):
        ax.axvline(val, color=c, linestyle=ls, linewidth=2 * s, zorder=6)
        right = j == len(marks) - 1  # the larger one is labelled on its right, the other on its left
        ax.annotate(f"{nm}: {vf(val)}", (val, 1), xycoords=("data", "axes fraction"),
                    xytext=((7 if right else -7) * s, -8 * s), textcoords="offset points",
                    ha="left" if right else "right", va="top",
                    fontsize=fr.fs(12), fontproperties=font("sans", "bold"), color=c)
    if xlabel:
        ax.set_xlabel(shape(xlabel), fontproperties=font("sans", "bold", xlabel), fontsize=fr.fs(13),
                      color=d.text_color, labelpad=8 * s)
    ax.set_ylabel(shape(ylabel or "Count"), fontproperties=font("sans", "bold", ylabel or "C"),
                  fontsize=fr.fs(13), color=d.text_color, labelpad=10 * s)
    return fr.finish()


# ======================================================================
def boxplot(data=None, values=None, *, x=None, y=None, colors=None, points=True,
            horizontal=False, ylabel=None, show_median=True, **kw):
    """Box plot comparing distributions of groups.

    boxplot({"2023": [...], "2024": [...]})   or   boxplot(df, x="Sector", y="Value")
    """
    opts = {k: kw.pop(k) for k in list(kw) if k in VALUE_OPTS}
    fr = Frame("boxplot", **kw)
    d, s = fr.design, fr.s
    import pandas as pd
    if isinstance(data, pd.DataFrame):
        if x is None:
            groups = {y: data[y].dropna().astype(float).tolist()}
        else:
            groups = {str(g): sub[y].dropna().astype(float).tolist()
                      for g, sub in data.groupby(x, sort=False)}
    elif isinstance(data, dict):
        groups = {str(k): [float(t) for t in v] for k, v in data.items()}
    elif values is not None:
        groups = {str(k): [float(t) for t in v] for k, v in zip(data, values)}
    else:
        groups = {"": [float(t) for t in data]}
    names = list(groups)
    n = len(names)
    allv = [t for g in groups.values() for t in g]
    vf = _vfmt(opts, allv)
    lab_fs = fr.fs(12.5)
    wrapped = [label(nm, 16) for nm in names]
    lines = max(w.count("\n") + 1 for w in wrapped)
    rect = fr.plot_rect(left=1.0 + (0.4 if ylabel else 0), right=0.5,
                        bottom=0.3 + lines * lab_fs * 1.35 / 72 / s, top=0.35)
    ax = fr.fig.add_axes(rect)
    lo, hi = min(allv), max(allv)
    span = (hi - lo) or 1
    ax.set_xlim(-0.6, n - 0.4)
    ax.set_ylim(lo - span * 0.08, hi + span * 0.1)
    style_axes(ax, fr, grid="y", baseline=False)
    ax.yaxis.set_major_formatter(_tick_fmt(allv))
    ax.set_xticks([])
    if ylabel:
        ax.set_ylabel(shape(ylabel), fontproperties=font("sans", "bold", ylabel), fontsize=fr.fs(13),
                      color=d.text_color, labelpad=10 * s)
    rng = np.random.default_rng(7)
    cols = colors or ([d.bar] * n)
    for i, nm in enumerate(names):
        v = np.asarray(groups[nm], dtype=float)
        if not len(v):
            continue
        q1, med, q3 = np.percentile(v, [25, 50, 75])
        iqr = q3 - q1
        lo_w = v[v >= q1 - 1.5 * iqr].min()
        hi_w = v[v <= q3 + 1.5 * iqr].max()
        c = cols[i % len(cols)]
        grad = tuple(c) if isinstance(c, (tuple, list)) else (c, c)
        ax.plot([i, i], [lo_w, q1], color=d.muted_color, linewidth=1.6 * s, zorder=2)
        ax.plot([i, i], [q3, hi_w], color=d.muted_color, linewidth=1.6 * s, zorder=2)
        for w_ in (lo_w, hi_w):
            ax.plot([i - 0.12, i + 0.12], [w_, w_], color=d.muted_color, linewidth=1.6 * s, zorder=2)
        bar(ax, i, q3 - q1, 0.5, grad, base=q1, radius_px=6 * s if d.rounded else 0, zorder=3)
        ax.plot([i - 0.25, i + 0.25], [med, med], color=d.accent, linewidth=3 * s, zorder=6,
                solid_capstyle="butt")
        if show_median:
            ax.annotate(vf(med), (i + 0.25, med), xytext=(6 * s, 0), textcoords="offset points",
                        va="center", fontsize=fr.fs(11.5), fontproperties=font("sans", "bold"),
                        color=d.value_color, zorder=8)
        out = v[(v < lo_w) | (v > hi_w)]
        ax.scatter(np.full(len(out), i), out, s=22 * s ** 2, facecolor="none", edgecolor=d.accent,
                   linewidth=1.2, zorder=5)
        if points and len(v) <= 400:
            jit = rng.uniform(-0.17, 0.17, len(v))
            ax.scatter(i + jit, v, s=10 * s ** 2, color=d.text_color, alpha=0.35, linewidth=0, zorder=4)
        ax.annotate(wrapped[i], (i, 0), xycoords=("data", "axes fraction"), xytext=(0, -8 * s),
                    textcoords="offset points", ha="center", va="top", fontsize=lab_fs,
                    fontproperties=font("sans", "regular", nm), color=d.text_color, annotation_clip=False)
    return fr.finish()


# ======================================================================
def scatterplot(data=None, yvalues=None, *, x=None, y=None, labels=None, size=None,
                groups=None, colors=None, trendline=True, flags="auto", flag_style=None,
                label_points="auto", xlabel=None, ylabel=None, **kw):
    """Scatter / bubble chart. Country labels are shown as flags automatically.

    scatterplot(x_values, y_values, labels=countries, size=population)
    scatterplot(df, x="Imports", y="Exports", labels="Country")
    """
    opts = {k: kw.pop(k) for k in list(kw) if k in VALUE_OPTS}
    fr = Frame("scatterplot", **kw)
    d, s = fr.design, fr.s
    import pandas as pd
    if isinstance(data, pd.DataFrame):
        xlabel = xlabel or x
        ylabel = ylabel or y
        xs = data[x].astype(float).tolist()
        ys = data[y].astype(float).tolist()
        labels = data[labels].tolist() if isinstance(labels, str) else labels
        size = data[size].astype(float).tolist() if isinstance(size, str) else size
        groups = data[groups].tolist() if isinstance(groups, str) else groups
    else:
        xs, ys = [float(t) for t in data], [float(t) for t in yvalues]
    xs, ys = np.asarray(xs), np.asarray(ys)
    n = len(xs)
    fl = resolve_flags(labels, flags) if labels is not None else None
    rect = fr.plot_rect(left=1.1 + (0.4 if ylabel else 0), right=0.6, bottom=0.8 + (0.35 if xlabel else 0),
                        top=0.7 if groups is not None else 0.35)
    ax = fr.fig.add_axes(rect)
    padx = (xs.max() - xs.min()) * 0.08 or 1
    pady = (ys.max() - ys.min()) * 0.1 or 1
    ax.set_xlim(xs.min() - padx, xs.max() + padx)
    ax.set_ylim(ys.min() - pady, ys.max() + pady)
    style_axes(ax, fr, grid="both", baseline=False)
    ax.grid(True, color=d.grid_color, alpha=d.grid_alpha, linewidth=0.8)
    ax.xaxis.set_major_formatter(_tick_fmt(list(xs)))
    ax.yaxis.set_major_formatter(_tick_fmt(list(ys)))
    if xlabel:
        ax.set_xlabel(shape(xlabel), fontproperties=font("sans", "bold", xlabel), fontsize=fr.fs(13),
                      color=d.text_color, labelpad=8 * s)
    if ylabel:
        ax.set_ylabel(shape(ylabel), fontproperties=font("sans", "bold", ylabel), fontsize=fr.fs(13),
                      color=d.text_color, labelpad=10 * s)
    if size is not None:
        sz = np.asarray(size, dtype=float)
        areas = 60 + 1400 * (sz / sz.max()) if sz.max() > 0 else np.full(n, 120)
    else:
        areas = np.full(n, 90.0)
    areas = areas * s ** 2
    if groups is not None:
        gnames = list(dict.fromkeys(groups))
        gcols = _series_colors(d, len(gnames), colors)
        pc = [gcols[gnames.index(g)] for g in groups]
    else:
        gnames = None
        pc = [d.accent] * n
    use_flags = fl is not None and all(get_flag(c, "round") is not None for c in fl if c)
    if use_flags:
        for i in range(n):
            img = get_flag(fl[i], flag_style or "round")
            fx, fy = to_fig(ax, xs[i], ys[i])
            fsize = float(np.sqrt(areas[i]) / 72 * 1.25) if size is not None else 0.32 * s
            place_image(ax, img, fx, fy, fsize, ring=d.surface, ring_width=1.5)
    else:
        ax.scatter(xs, ys, s=areas, c=pc, alpha=0.85 if size is not None else 1,
                   edgecolor=d.surface, linewidth=1.5, zorder=5)
    if trendline and n >= 3:
        m, b = np.polyfit(xs, ys, 1)
        r = np.corrcoef(xs, ys)[0, 1]
        xx = np.array(ax.get_xlim())
        ax.plot(xx, m * xx + b, color=d.muted_color, linestyle="--", linewidth=1.6 * s, zorder=3)
        ax.text(0.99, 0.02, f"r = {r:.2f}", transform=ax.transAxes, ha="right", va="bottom",
                fontsize=fr.fs(12), fontproperties=font("sans", "bold"), color=d.muted_color)
    if labels is not None and label_points:
        if label_points == "auto":
            order = np.argsort(-(ys - ys.mean()) / (ys.std() or 1) - (xs - xs.mean()) / (xs.std() or 1))
            pick = list(range(n)) if n <= 15 else list(order[:6]) + list(order[-4:])
        else:
            pick = range(n)
        from ._draw import LabelPlacer
        lp = LabelPlacer(fr.fig)
        for i in range(n):  # the points themselves are obstacles
            fx, fy = to_fig(ax, xs[i], ys[i])
            r_in = (0.3 * s) if use_flags and size is None else float(np.sqrt(areas[i]) / 72)
            lp.reserve_fig_rect(fx, fy, r_in, r_in)
        for i in pick:
            off = (np.sqrt(areas[i]) / 2 + 4) if not use_flags else (0.2 * s * 72)
            t = ax.annotate(label(labels[i], 20), (xs[i], ys[i]), xytext=(off, 0), textcoords="offset points",
                            va="center", ha="left", fontsize=fr.fs(11),
                            fontproperties=font("sans", "regular", labels[i]), color=d.text_color, zorder=9)
            lp.try_text(t, [((off, 0), "left", "center"), ((-off, 0), "right", "center"),
                            ((0, off), "center", "bottom"), ((0, -off), "center", "top")])
    if gnames:
        draw_legend(fr, ax, [str(g) for g in gnames], gcols, y_axes=1.0 + 0.35 * s / (rect[3] * fr.H))
    return fr.finish()


# ======================================================================
def heatmap(data, *, rows=None, columns=None, values=None, cmap=None, annotate=True,
            **kw):
    """Heatmap from a DataFrame (rows x columns) or a long table with rows=, columns=, values=."""
    opts = {k: kw.pop(k) for k in list(kw) if k in VALUE_OPTS}
    fr = Frame("heatmap", **kw)
    d, s = fr.design, fr.s
    import pandas as pd
    if rows and columns and values:
        tab = data.pivot_table(index=rows, columns=columns, values=values, aggfunc="sum")
    elif isinstance(data, pd.DataFrame):
        tab = data
    else:
        tab = pd.DataFrame(data)
    M = tab.to_numpy(dtype=float)
    r, c = M.shape
    rl = [label(str(v), 26) for v in tab.index]
    cl = [label(str(v), 12) for v in tab.columns]
    left = max(_text_width_in(fr, t, fr.fs(12)) for t in rl) / s + 0.4
    rect = fr.plot_rect(left=left, right=0.4, bottom=0.3, top=0.55)
    ax = fr.fig.add_axes(rect)
    cm = cmap or LinearSegmentedColormap.from_list("h", list(d.sequential))
    im = ax.imshow(M, cmap=cm, aspect="auto")
    ax.set_xticks(range(c))
    ax.set_xticklabels(cl, fontsize=fr.fs(12))
    ax.xaxis.tick_top()
    ax.set_yticks(range(r))
    ax.set_yticklabels(rl, fontsize=fr.fs(12))
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(length=0, colors=d.text_color)
    for t in ax.get_xticklabels() + ax.get_yticklabels():
        t.set_color(d.text_color)
        t.set_fontproperties(font("sans", "regular", t.get_text()))
        t.set_fontsize(fr.fs(12))
    ax.set_xticks(np.arange(-0.5, c), minor=True)
    ax.set_yticks(np.arange(-0.5, r), minor=True)
    ax.grid(which="minor", color=d.surface, linewidth=2.5 * s)
    ax.tick_params(which="minor", length=0)
    vf = _vfmt(opts, list(M[~np.isnan(M)]))
    if annotate and r * c <= 300:
        norm = im.norm
        for i in range(r):
            for j in range(c):
                if M[i, j] == M[i, j]:
                    col = cm(norm(M[i, j]))
                    ax.text(j, i, vf(M[i, j]), ha="center", va="center",
                            fontsize=fr.fs(11 if r * c < 80 else 8.5), fontproperties=font("sans", "bold"),
                            color=text_color_on(col))
    return fr.finish()
