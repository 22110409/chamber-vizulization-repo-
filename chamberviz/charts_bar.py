"""Bar charts, grouped/stacked bars, dot/lollipop/dumbbell plots and treemaps."""
from __future__ import annotations

import numpy as np
from matplotlib.ticker import FuncFormatter, MaxNLocator

from . import config
from ._draw import (bar, draw_icon, readable_on, get_flag, place_image, resolve_flags, resolve_icons,
                    style_axes, text_color_on, to_fig, xy)
from .canvas import Frame
from .text import auto_decimals, fmt, font, has_arabic, label, shape

VALUE_OPTS = {"decimals", "value_prefix", "value_suffix", "compact", "value_format"}


def _vfmt(opts, values):
    dec = opts.get("decimals")
    if dec is None:
        dec = auto_decimals(values)
    return lambda v: fmt(v, dec, opts.get("value_prefix", ""), opts.get("value_suffix", ""),
                         opts.get("compact", False), value_format=opts.get("value_format"))


def _tick_fmt(values, compact=None):
    m = max([abs(v) for v in values] or [1])
    compact = (m >= 1e6) if compact is None else compact
    dec = 0 if m >= 10 else 1
    return FuncFormatter(lambda v, _: fmt(v, dec if not compact else 1, compact=compact))


def _nice_limits(values, headroom=1.12):
    """Axis limits with a little room above the tallest bar for its value label."""
    vmin, vmax = min(list(values) + [0]), max(list(values) + [0])
    span = (vmax - vmin) or 1.0
    lo = vmin - span * (headroom - 1) if vmin < 0 else 0
    hi = vmax + span * (headroom - 1) if vmax > 0 else 0
    return lo, hi


def _highlight_idx(highlight, labels, values):
    if highlight in (None, False):
        return set()
    items = highlight if isinstance(highlight, (list, tuple, set)) else [highlight]
    out = set()
    for h in items:
        if h == "max":
            out.add(int(np.argmax(values)))
        elif h == "min":
            out.add(int(np.argmin(values)))
        elif h == "first":
            out.add(0)
        elif h == "last":
            out.add(len(values) - 1)
        elif isinstance(h, (int, np.integer)):
            out.add(int(h) % len(values))
        elif h in labels:
            out.add(labels.index(h))
    return out


def _bar_colors(bars, n, design, hi):
    """-> list of (bottom, top) gradients."""
    if bars is None:
        return [design.highlight if i in hi else design.bar for i in range(n)]
    if isinstance(bars, str):
        return [design.highlight if i in hi else (bars, bars) for i in range(n)]
    if isinstance(bars, tuple) and len(bars) == 2 and all(isinstance(c, str) for c in bars):
        return [design.highlight if i in hi else bars for i in range(n)]
    lst = list(bars)
    out = []
    for i in range(n):
        c = lst[i % len(lst)]
        out.append(tuple(c) if isinstance(c, (tuple, list)) else (c, c))
    return out


def _sort(labels, values, sort, top, extra=None):
    idx = list(range(len(values)))
    if sort in ("desc", "descending", True):
        idx.sort(key=lambda i: -values[i])
    elif sort in ("asc", "ascending"):
        idx.sort(key=lambda i: values[i])
    if top:
        idx = idx[:top]
    labels = [labels[i] for i in idx]
    values = [values[i] for i in idx]
    extra = [None if e is None else [e[i] for i in idx] for e in (extra or [])]
    return labels, values, extra


def _text_width_in(frame, s, size):
    t = frame.fig.text(0, 0, s, fontproperties=font("sans", "bold", s), fontsize=size)
    w = t.get_window_extent(renderer=frame.fig.canvas.get_renderer()).width / frame.fig.dpi
    t.remove()
    return w


# ======================================================================
def barplot(data=None, values=None, *, x=None, y=None, horizontal=False, bars=None,
            highlight="max", sort=None, top=None, flags="auto", flag_style=None,
            icons=None, icon_variant="outline", value_labels=True, show_axis=None,
            show_grid=None, xlabel=None, ylabel=None, ymax=None, bar_width=0.72,
            label_wrap=None, rtl=False, rounded=None, shadow=None, glow=None, **kw):
    """Bar chart. The simplest call:  barplot(["A", "B"], [10, 20], title="...")

    bars       : one colour, a (bottom, top) gradient, or a list of colours per bar
    highlight  : "max" (default), "min", an index, a label, a list, or None
    flags      : "auto" (flags when labels are countries), True, False, or a list of countries
    icons      : "auto" (guess from labels), a list of icon names, or a dict {label: icon}
    horizontal : True for horizontal bars (good for long labels / many items)
    """
    opts = {k: kw.pop(k) for k in list(kw) if k in VALUE_OPTS}
    fr = Frame("barplot", **kw)
    d, s = fr.design, fr.s
    labels, vals = xy(data, values, x, y, "barplot")
    fl = resolve_flags(labels, flags)
    ic = resolve_icons(labels, icons)
    labels, vals, (fl, ic) = _sort(labels, vals, sort, top, [fl, ic])
    n = len(vals)
    hi = _highlight_idx(highlight if not (isinstance(bars, list) and highlight == "max") else None,
                        labels, vals)
    grads = _bar_colors(bars, n, d, hi)
    vf = _vfmt(opts, vals)
    fstyle = flag_style or config.DEFAULTS["flag_style"]
    rounded = d.rounded if rounded is None else rounded
    shadow = d.shadow if shadow is None else shadow
    glow = d.glow if glow is None else glow
    arabic = any(has_arabic(l) for l in labels)
    lab_fs = fr.fs(13 if n <= 8 else 11.5)
    flag_in = (0.30 if n <= 8 else 0.24) * s

    if horizontal:
        return _barh(fr, labels, vals, grads, hi, fl, ic, vf, fstyle, rounded, shadow, glow,
                     arabic, lab_fs, flag_in, icon_variant, value_labels, show_axis, show_grid,
                     xlabel, ymax, bar_width, label_wrap, rtl, n)

    # ---------------- vertical
    left_in = 1.0 + (0.45 if ylabel else 0)
    avail = (fr.W - (left_in + 0.4) * s) / max(n, 1)
    wrap = label_wrap or max(8, int(avail * 72 / (lab_fs * 0.56)))
    wrapped = [label(l, wrap) for l in labels]
    lines = max((w.count("\n") + 1 for w in wrapped), default=1)
    flags_above = fl is not None and (lines > 1 or not arabic)
    bottom_in = 0.25 + lines * lab_fs * 1.35 / 72 / s + ((flag_in / s + 0.12) if flags_above else 0)
    if fl is not None and not flags_above:
        bottom_in = max(bottom_in, 0.3 + flag_in / s)
    rect = fr.plot_rect(left=left_in if not rtl else 0.5, right=0.45 if not rtl else left_in,
                        bottom=bottom_in, top=0.45)
    ax = fr.fig.add_axes(rect)
    order = list(range(n))[::-1] if rtl else list(range(n))
    pos = {i: order.index(i) for i in range(n)}
    ax.set_xlim(-0.6, n - 0.4)
    lo, hi_lim = _nice_limits(vals)
    ax.set_ylim(lo, ymax or hi_lim)
    style_axes(ax, fr, grid="y" if (show_grid is None or show_grid) else None,
               show_axis=show_axis is not False)
    ax.yaxis.set_major_formatter(_tick_fmt(vals))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6, steps=[1, 2, 2.5, 5, 10]))
    if rtl:
        ax.yaxis.tick_right()
    ax.set_xticks([])
    if ylabel:
        ax.set_ylabel(shape(ylabel), fontproperties=font("sans", "bold", ylabel),
                      fontsize=fr.fs(17), color=d.text_color, labelpad=14 * s)
        if rtl:
            ax.yaxis.set_label_position("right")
    if xlabel:
        fr.fig.text(rect[0] + rect[2] / 2, (fr.footer_h + 0.05) / fr.H, shape(xlabel), ha="center",
                    fontproperties=font("sans", "bold", xlabel), fontsize=fr.fs(13), color=d.text_color)
    sx, sy = None, None
    from ._draw import px_scale
    sx, sy = px_scale(ax)
    rend = fr.fig.canvas.get_renderer()
    for i, v in enumerate(vals):
        p = pos[i]
        is_hi = i in hi
        bar(ax, p, v, bar_width, grads[i], radius_px=(10 * s * fr.fig.dpi / 100) if rounded else 0,
            cap=(d.highlight_cap if is_hi else d.bar_cap) or None, cap_width=2.2 * s,
            shadow=shadow, glow=(grads[i][1] if (glow and is_hi) else None))
        bar_px = abs(v) * sy
        icon_pt = fr.fs(34 if n <= 8 else 24)
        value_dy = 7 * s
        if ic and ic[i]:
            col = readable_on(d.highlight_icon_color if is_hi else d.icon_color, grads[i][1])
            if bar_px > icon_pt * 1.39 * 2.1:
                draw_icon(ax, ic[i], p, v, icon_pt, col, icon_variant,
                          dy_pt=-(icon_pt * 0.95) if v >= 0 else icon_pt * 0.95)
            else:
                draw_icon(ax, ic[i], p, v, icon_pt * 0.7, d.icon_color, icon_variant,
                          dy_pt=(icon_pt * 0.55 + 6 * s))
                value_dy += icon_pt * 0.95
        if value_labels:
            ax.annotate(vf(v), (p, v), xytext=(0, value_dy if v >= 0 else -value_dy),
                        textcoords="offset points", ha="center",
                        va="bottom" if v >= 0 else "top",
                        fontproperties=font("sans", "bold"), fontsize=fr.fs(17 if n <= 8 else 13),
                        color=d.highlight_value_color if is_hi else d.value_color, zorder=7,
                        annotation_clip=False)
        # category label (+ flag)
        f_img = get_flag(fl[i], fstyle) if fl is not None else None
        txt_off = 8 * s
        if fl is not None and flags_above:
            fx, fy = to_fig(ax, p, 0, dy_in=-(0.1 * s + flag_in / 2), ycoord="axes")
            fy_axes = fy
            if f_img is not None:
                place_image(ax, f_img, fx, fy_axes, flag_in)
            elif fl[i]:
                draw_icon(ax, "world", p, 0, flag_in * 72 * 0.9, d.muted_color, xycoords=("data", "axes fraction"),
                          dy_pt=-(0.1 * s + flag_in / 2) * 72)
            txt_off = (0.1 * s + flag_in + 0.08 * s) * 72
        t = ax.annotate(wrapped[i], (p, 0), xycoords=("data", "axes fraction"), xytext=(0, -txt_off),
                        textcoords="offset points", ha="center", va="top",
                        fontproperties=font("sans", "bold" if arabic else "regular", labels[i]),
                        fontsize=lab_fs, color=d.text_color, linespacing=1.25, annotation_clip=False)
        if fl is not None and not flags_above:
            bb = t.get_window_extent(renderer=rend)
            gap = 0.08 * s
            shift = (flag_in + gap) / 2
            # move text so text+flag are centred together
            t.set_position((-shift * 72 if arabic else shift * 72, -txt_off))
            bb = t.get_window_extent(renderer=rend)
            inv = fr.fig.transFigure.inverted()
            (x0, y0), (x1, y1) = inv.transform([(bb.x0, bb.y0), (bb.x1, bb.y1)])
            fx = (x1 + (gap + flag_in / 2) / fr.W) if arabic else (x0 - (gap + flag_in / 2) / fr.W)
            fy = (y0 + y1) / 2
            if f_img is not None:
                place_image(ax, f_img, fx, fy, flag_in)
    return fr.finish()


def _barh(fr, labels, vals, grads, hi, fl, ic, vf, fstyle, rounded, shadow, glow, arabic,
          lab_fs, flag_in, icon_variant, value_labels, show_axis, show_grid, xlabel, xmax,
          bar_width, label_wrap, rtl, n):
    d, s = fr.design, fr.s
    rtl = rtl or False
    wrap = label_wrap or 30
    wrapped = [label(l, wrap) for l in labels]
    lab_w = max((_text_width_in(fr, w, lab_fs) for w in wrapped), default=1.0)
    side_in = (lab_w + 0.35 * s + ((flag_in + 0.12 * s) if fl is not None else 0)) / s
    lab_fs_v = fr.fs(15 if n <= 10 else 12)
    val_room = 0.9
    rect = fr.plot_rect(left=side_in if not rtl else val_room, right=val_room if not rtl else side_in,
                        bottom=0.35 if not (show_axis or show_grid) else 0.6, top=0.3)
    ax = fr.fig.add_axes(rect)
    lo, hi_lim = _nice_limits(vals, 1.06)
    ax.set_xlim(lo, xmax or hi_lim)
    ax.set_ylim(-0.6, n - 0.4)
    if rtl:
        ax.invert_xaxis()
    style_axes(ax, fr, grid="x" if show_grid else None, show_axis=bool(show_axis), baseline=True,
               baseline_side="left")
    if rtl:
        ax.spines["left"].set_visible(False)
        ax.spines["right"].set_visible(True)
        ax.spines["right"].set_color(d.axis_color)
        ax.spines["right"].set_linewidth(1.4 * s)
    ax.xaxis.set_major_formatter(_tick_fmt(vals))
    if not show_axis:
        ax.set_xticks([])
    ax.set_yticks([])
    if xlabel:
        ax.set_xlabel(shape(xlabel), fontproperties=font("sans", "bold", xlabel),
                      fontsize=fr.fs(13), color=d.text_color)
    rend = fr.fig.canvas.get_renderer()
    for i, v in enumerate(vals):
        p = n - 1 - i
        is_hi = i in hi
        bar(ax, p, v, bar_width, grads[i], horizontal=True,
            radius_px=(8 * s * fr.fig.dpi / 100) if rounded else 0,
            cap=(d.highlight_cap if is_hi else d.bar_cap) or None, cap_width=2.2 * s,
            shadow=shadow, glow=(grads[i][1] if (glow and is_hi) else None))
        sign = -1 if rtl else 1
        icon_pt = fr.fs(20 if n <= 10 else 14)
        v_off = 8 * s
        if ic and ic[i]:
            col = readable_on(d.highlight_icon_color if is_hi else d.icon_color, grads[i][1])
            from ._draw import px_scale
            sx, _ = px_scale(ax)
            if abs(v) * sx > icon_pt * 1.39 * 2.2:
                draw_icon(ax, ic[i], v, p, icon_pt, col, icon_variant, dx_pt=-sign * icon_pt * 0.9)
            else:
                draw_icon(ax, ic[i], v, p, icon_pt, d.icon_color, icon_variant, dx_pt=sign * (icon_pt * 0.7 + 4))
                v_off += icon_pt * 1.3
        if value_labels:
            ax.annotate(vf(v), (v, p), xytext=(sign * v_off, 0), textcoords="offset points",
                        ha="left" if sign > 0 else "right", va="center",
                        fontproperties=font("sans", "bold"), fontsize=lab_fs_v,
                        color=d.highlight_value_color if is_hi else d.value_color,
                        annotation_clip=False, zorder=7)
        # label on the axis side
        ax_x = 1 if rtl else 0
        gap_pt = 10 * s
        f_img = get_flag(fl[i], fstyle) if fl is not None else None
        lab_off = gap_pt + ((flag_in * 72 + 8 * s) if fl is not None else 0)
        ax.annotate(wrapped[i], (ax_x, p), xycoords=("axes fraction", "data"),
                    xytext=(lab_off if rtl else -lab_off, 0), textcoords="offset points",
                    ha="left" if rtl else "right", va="center",
                    fontproperties=font("sans", "bold" if arabic else "regular", labels[i]),
                    fontsize=lab_fs, color=d.text_color, annotation_clip=False, linespacing=1.2)
        if f_img is not None:
            off_in = (gap_pt / 72 + flag_in / 2)
            fx, fy = to_fig(ax, ax_x, p, dx_in=off_in if rtl else -off_in, xcoord="axes")
            place_image(ax, f_img, fx, fy, flag_in)
    return fr.finish()


# ======================================================================
def multibarplot(data=None, series=None, *, x=None, y=None, stacked=False, colors=None,
                 horizontal=False, value_labels="auto", show_grid=True, ylabel=None,
                 legend=True, label_wrap=None, bar_width=0.8, rounded=None, **kw):
    """Grouped or stacked bars.  multibarplot(["Q1","Q2"], {"2024": [1,2], "2025": [2,3]})"""
    opts = {k: kw.pop(k) for k in list(kw) if k in VALUE_OPTS}
    fr = Frame("multibarplot", **kw)
    d, s = fr.design, fr.s
    if series is None:
        from ._draw import series_input
        cats, series = series_input(data, x, y)
    else:
        cats = list(data)
    names = list(series)
    k, n = len(names), len(cats)
    cols = colors or d.series
    allv = [v for nm in names for v in series[nm]]
    vf = _vfmt(opts, allv)
    rounded = d.rounded if rounded is None else rounded
    lab_fs = fr.fs(13 if n <= 8 else 11)
    avail = (fr.W - 1.4 * s) / max(n, 1)
    wrapped = [label(c, label_wrap or max(8, int(avail * 72 / (lab_fs * 0.56)))) for c in cats]
    lines = max(w.count("\n") + 1 for w in wrapped)
    rect = fr.plot_rect(left=1.0 + (0.45 if ylabel else 0), right=0.4,
                        bottom=0.3 + lines * lab_fs * 1.35 / 72 / s, top=0.75 if legend else 0.35)
    ax = fr.fig.add_axes(rect)
    totals = [sum(series[nm][i] for nm in names) for i in range(n)]
    lo, top = _nice_limits(totals if stacked else allv)
    ax.set_xlim(-0.6, n - 0.4)
    ax.set_ylim(lo, top)
    style_axes(ax, fr, grid="y" if show_grid else None)
    ax.yaxis.set_major_formatter(_tick_fmt(allv))
    ax.set_xticks([])
    if ylabel:
        ax.set_ylabel(shape(ylabel), fontproperties=font("sans", "bold", ylabel), fontsize=fr.fs(15),
                      color=d.text_color, labelpad=12 * s)
    from ._draw import px_scale
    sx, sy = px_scale(ax)
    show_vals = (n * (1 if stacked else k) <= 28) if value_labels == "auto" else value_labels
    for i in range(n):
        base = 0.0
        for j, nm in enumerate(names):
            v = series[nm][i]
            c = cols[j % len(cols)]
            grad = tuple(c) if isinstance(c, (tuple, list)) else (c, c)
            if stacked:
                bar(ax, i, v, bar_width * 0.75, grad, base=base, outline=False,
                    edge=d.surface, radius_px=0)
                if show_vals and abs(v) * sy > fr.fs(11) * 1.8:
                    ax.text(i, base + v / 2, vf(v), ha="center", va="center", fontsize=fr.fs(10.5),
                            fontproperties=font("sans", "bold"), color=text_color_on(grad[1]), zorder=8)
                base += v
            else:
                w = bar_width / k
                p = i - bar_width / 2 + w * (j + 0.5)
                bar(ax, p, v, w * 0.9, grad, radius_px=(6 * s) if rounded else 0, outline=False)
                if show_vals:
                    ax.annotate(vf(v), (p, v), xytext=(0, 4 * s), textcoords="offset points",
                                ha="center", va="bottom", fontsize=fr.fs(11 if k * n < 16 else 9),
                                fontproperties=font("sans", "bold"), color=d.value_color,
                                annotation_clip=False, zorder=8)
        if stacked and show_vals:
            ax.annotate(vf(totals[i]), (i, totals[i]), xytext=(0, 5 * s), textcoords="offset points",
                        ha="center", va="bottom", fontsize=fr.fs(13), fontproperties=font("sans", "bold"),
                        color=d.value_color, annotation_clip=False)
        ax.annotate(wrapped[i], (i, 0), xycoords=("data", "axes fraction"), xytext=(0, -8 * s),
                    textcoords="offset points", ha="center", va="top", fontsize=lab_fs,
                    fontproperties=font("sans", "regular", cats[i]), color=d.text_color,
                    annotation_clip=False)
    if legend:
        draw_legend(fr, ax, names, cols, y_axes=1.0 + 0.18 * s / (rect[3] * fr.H) * 2)
    return fr.finish()


def draw_legend(fr, ax, names, colors, y_axes=1.06, marker="square"):
    """A centred single-row legend above the axes."""
    d, s = fr.design, fr.s
    rend = fr.fig.canvas.get_renderer()
    sw = 0.16 * s
    gap = 0.12 * s
    widths = [_text_width_in(fr, shape(nm), fr.fs(12)) for nm in names]
    total = sum(widths) + len(names) * (sw + gap + 0.3 * s)
    bb = ax.get_position()
    cx = (bb.x0 + bb.width / 2) * fr.W
    xx = cx - total / 2
    fy = bb.y0 + y_axes * bb.height
    for nm, c, w in zip(names, colors, widths):
        c = c[1] if isinstance(c, (tuple, list)) else c
        fx = xx / fr.W
        if marker == "line":
            fr.fig.add_artist(__import__("matplotlib").lines.Line2D(
                [fx, fx + sw / fr.W], [fy, fy], color=c, linewidth=3 * s, transform=fr.fig.transFigure))
        else:
            from matplotlib.patches import FancyBboxPatch
            fr.fig.add_artist(FancyBboxPatch((fx, fy - sw / 2 / fr.H), sw / fr.W, sw / fr.H,
                                             boxstyle="round,pad=0,rounding_size=0.002",
                                             transform=fr.fig.transFigure, facecolor=c, edgecolor="none"))
        fr.fig.text(fx + (sw + gap) / fr.W, fy, shape(nm), va="center", ha="left",
                    fontproperties=font("sans", "regular", nm), fontsize=fr.fs(12), color=d.text_color)
        xx += sw + gap + w + 0.3 * s


# ======================================================================
def dotplot(data=None, values=None, *, x=None, y=None, compare=None, names=None,
            sort="desc", top=None, flags="auto", flag_style=None, show_change=True,
            color=None, compare_color=None, label_wrap=30, **kw):
    """Lollipop chart, or a dumbbell chart when compare= (e.g. last year's values) is given.

    dotplot(countries, values_2025, compare=values_2024, names=("2024", "2025"))
    """
    opts = {k: kw.pop(k) for k in list(kw) if k in VALUE_OPTS}
    fr = Frame("dotplot", **kw)
    d, s = fr.design, fr.s
    labels, vals = xy(data, values, x, y, "dotplot")
    comp = list(compare) if compare is not None else None
    fl = resolve_flags(labels, flags)
    labels, vals, (fl, comp) = _sort(labels, vals, sort, top, [fl, comp])
    n = len(vals)
    vf = _vfmt(opts, vals + (comp or []))
    arabic = any(has_arabic(l) for l in labels)
    lab_fs = fr.fs(13 if n <= 12 else 11)
    flag_in = 0.24 * s
    wrapped = [label(l, label_wrap) for l in labels]
    lab_w = max(_text_width_in(fr, w, lab_fs) for w in wrapped)
    left = (lab_w + 0.35 * s + ((flag_in + 0.1 * s) if fl else 0)) / s
    rect = fr.plot_rect(left=left, right=1.3 if (comp and show_change) else 0.9, bottom=0.6,
                        top=0.75 if comp else 0.3)
    ax = fr.fig.add_axes(rect)
    allv = vals + (comp or [])
    lo, hi_lim = _nice_limits(allv, 1.08)
    if comp:
        span = max(allv) - min(allv)
        lo = max(0, min(allv) - span * 0.15) if min(allv) >= 0 else min(allv) - span * 0.1
    ax.set_xlim(lo, hi_lim)
    ax.set_ylim(-0.7, n - 0.3)
    style_axes(ax, fr, grid="x", baseline=False)
    ax.xaxis.set_major_formatter(_tick_fmt(allv))
    ax.set_yticks([])
    c_main = color or d.highlight[1]
    c_comp = compare_color or (d.bar[1] if d.bar[1] != d.bar[0] else d.muted_color)
    ms = (110 if n <= 15 else 70) * s ** 2
    for i, v in enumerate(vals):
        p = n - 1 - i
        ax.axhline(p, color=d.grid_color, alpha=d.grid_alpha * 0.8, linewidth=0.8, zorder=1)
        if comp:
            c = comp[i]
            ax.plot([c, v], [p, p], color=d.muted_color, alpha=0.6, linewidth=3.5 * s,
                    solid_capstyle="round", zorder=2)
            ax.scatter([c], [p], s=ms, color=c_comp, edgecolor=d.surface, linewidth=1.5, zorder=4)
            ax.scatter([v], [p], s=ms, color=c_main, edgecolor=d.surface, linewidth=1.5, zorder=5)
            right = max(v, c)
            ax.annotate(vf(v), (right, p), xytext=(10 * s, 0), textcoords="offset points",
                        va="center", fontsize=fr.fs(11.5), fontproperties=font("sans", "bold"),
                        color=d.value_color, annotation_clip=False)
            if show_change and c:
                ch = (v - c) / abs(c) * 100
                ax.annotate(f"{ch:+.1f}%", (1, p), xycoords=("axes fraction", "data"), xytext=(12 * s, 0),
                            textcoords="offset points", va="center", ha="left", fontsize=fr.fs(12),
                            fontproperties=font("sans", "bold"),
                            color=d.positive if ch >= 0 else d.negative, annotation_clip=False)
        else:
            ax.plot([lo, v], [p, p], color=d.bar[1], linewidth=2.2 * s, zorder=2, alpha=0.9)
            ax.scatter([v], [p], s=ms, color=c_main, edgecolor=d.surface, linewidth=1.5, zorder=5)
            ax.annotate(vf(v), (v, p), xytext=(11 * s, 0), textcoords="offset points", va="center",
                        fontsize=fr.fs(12), fontproperties=font("sans", "bold"), color=d.value_color,
                        annotation_clip=False)
        off = 10 * s + ((flag_in * 72 + 6 * s) if fl else 0)
        ax.annotate(wrapped[i], (0, p), xycoords=("axes fraction", "data"), xytext=(-off, 0),
                    textcoords="offset points", ha="right", va="center", fontsize=lab_fs,
                    fontproperties=font("sans", "bold" if arabic else "regular", labels[i]),
                    color=d.text_color, annotation_clip=False)
        if fl:
            img = get_flag(fl[i], flag_style or config.DEFAULTS["flag_style"])
            if img is not None:
                fx, fy = to_fig(ax, 0, p, dx_in=-(10 * s / 72 + flag_in / 2), xcoord="axes")
                place_image(ax, img, fx, fy, flag_in)
    if comp:
        nm = names or ("Before", "After")
        draw_legend(fr, ax, list(nm), [c_comp, c_main], y_axes=1.0 + 0.4 * s / (rect[3] * fr.H))
    return fr.finish()


# ======================================================================
def _squarify(values, x, y, w, h):
    """Squarified treemap layout -> list of (x, y, w, h) in the input order (values sorted desc)."""
    rects = []
    vals = list(values)
    total = sum(vals)
    if total <= 0:
        return rects
    scale = w * h / total
    areas = [v * scale for v in vals]

    def worst(row, side):
        s_ = sum(row)
        return max(max(side ** 2 * r / s_ ** 2, s_ ** 2 / (side ** 2 * r)) for r in row)

    i = 0
    while i < len(areas):
        side = min(w, h)
        row = [areas[i]]
        i += 1
        while i < len(areas) and worst(row + [areas[i]], side) <= worst(row, side):
            row.append(areas[i])
            i += 1
        s_ = sum(row)
        if w >= h:
            cw = s_ / h
            yy = y
            for a in row:
                rects.append((x, yy, cw, a / cw))
                yy += a / cw
            x += cw
            w -= cw
        else:
            ch = s_ / w
            xx = x
            for a in row:
                rects.append((xx, y, a / ch, ch))
                xx += a / ch
            y += ch
            h -= ch
    return rects


def treemap(data=None, values=None, *, x=None, y=None, colors=None, highlight="max",
            flags="auto", icons=None, flag_style=None, show_percent=True, label_wrap=18, **kw):
    """Treemap of shares, e.g. imports by commodity."""
    opts = {k: kw.pop(k) for k in list(kw) if k in VALUE_OPTS}
    fr = Frame("treemap", **kw)
    d, s = fr.design, fr.s
    labels, vals = xy(data, values, x, y, "treemap")
    fl = resolve_flags(labels, flags)
    ic = resolve_icons(labels, icons)
    labels, vals, (fl, ic) = _sort(labels, vals, "desc", None, [fl, ic])
    vf = _vfmt(opts, vals)
    total = sum(vals)
    rect = fr.plot_rect(left=0.4, right=0.4, bottom=0.2, top=0.2)
    ax = fr.fig.add_axes(rect)
    Wd, Hd = rect[2] * fr.W, rect[3] * fr.H
    ax.set_xlim(0, Wd)
    ax.set_ylim(0, Hd)
    ax.axis("off")
    hi = _highlight_idx(highlight, labels, vals)
    rects = _squarify(vals, 0, 0, Wd, Hd)
    gap = 0.03 * s
    for i, (rx, ry, rw, rh) in enumerate(rects):
        if colors:
            c = colors[i % len(colors)]
            grad = tuple(c) if isinstance(c, (tuple, list)) else (c, c)
        else:
            grad = d.highlight if i in hi else d.bar
        ry2 = Hd - ry - rh  # fill from the top-left
        from matplotlib.patches import FancyBboxPatch
        from matplotlib.colors import LinearSegmentedColormap
        clip = FancyBboxPatch((rx + gap, ry2 + gap), rw - 2 * gap, rh - 2 * gap,
                              boxstyle=f"round,pad=0,rounding_size={0.06 * s if d.rounded else 0.001}",
                              facecolor="none", edgecolor=(1, 1, 1, 0.12), linewidth=1, zorder=3)
        ax.add_patch(clip)
        im = ax.imshow(np.linspace(0, 1, 128).reshape(-1, 1), aspect="auto", origin="lower",
                       cmap=LinearSegmentedColormap.from_list("t", list(grad)),
                       extent=[rx, rx + rw, ry2, ry2 + rh], zorder=2)
        im.set_clip_path(clip)
        tc = text_color_on(grad[1])      # text at the top sits on the top colour
        tc2 = text_color_on(grad[0])     # value at the bottom sits on the bottom colour
        if rw < 0.55 * s or rh < 0.4 * s:
            continue
        fsz = fr.fs(float(np.clip(min(rw, rh) * 9 / s, 9, 17)))
        pad = 0.12 * s
        tx, ty = rx + pad, ry2 + rh - pad
        if fl and get_flag(fl[i], flag_style or "round") is not None and rh > 0.9 * s:
            fsize = min(0.34 * s, rh * 0.25)
            fx, fy = to_fig(ax, tx + fsize / 2, ty - fsize / 2)
            place_image(ax, get_flag(fl[i], flag_style or "round"), fx, fy, fsize)
            ty -= fsize + 0.08 * s
        elif ic and ic[i] and rh > 0.9 * s:
            draw_icon(ax, ic[i], tx, ty, fsz * 1.6, d.icon_color if i not in hi else d.highlight_icon_color,
                      ha="left", va="top")
            ty -= fsz * 1.9 / 72
        wrapw = max(6, int((rw - 2 * pad) * 72 / (fsz * 0.62)))
        ax.text(tx, ty, label(labels[i], min(label_wrap, wrapw)), ha="left", va="top", fontsize=fsz,
                fontproperties=font("sans", "bold", labels[i]), color=tc, zorder=5, linespacing=1.15)
        pct = f"  ({vals[i] / total * 100:.1f}%)" if show_percent else ""
        ax.text(tx, ry2 + pad, vf(vals[i]) + pct, ha="left", va="bottom", fontsize=fsz * 0.85,
                fontproperties=font("sans", "regular"), color=tc2, zorder=5, alpha=0.9)
    return fr.finish()
