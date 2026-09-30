"""KPI cards: big headline numbers with change arrows and icons."""
from __future__ import annotations

from matplotlib.patches import FancyBboxPatch

from ._draw import draw_icon, get_flag, place_image
from .canvas import Frame
from .text import fmt, font, has_arabic, shape, wrap


def kpi_cards(cards, *, columns=None, decimals=1, **kw):
    """Headline numbers as cards.

    kpi_cards([
        {"label": "Total imports", "value": 18_950.3, "unit": "JD million", "change": 4.2, "icon": "package-import"},
        {"label": "Total exports", "value": 9_120.8, "unit": "JD million", "change": -1.5, "icon": "package-export"},
        {"label": "Top partner", "value": "China", "flag": "China"},
    ], title="Trade at a glance 2025")

    Each card: label, value (number or text), optional unit, change (%), icon, flag, note.
    """
    fr = Frame("kpi_cards", **kw)
    d, s = fr.design, fr.s
    n = len(cards)
    cols = columns or (n if n <= 4 else (3 if n in (5, 6, 9) else 4))
    rows = -(-n // cols)
    rect = fr.plot_rect(left=0.5, right=0.5, bottom=0.25, top=0.2)
    ax = fr.fig.add_axes(rect)
    Wd, Hd = rect[2] * fr.W, rect[3] * fr.H
    ax.set_xlim(0, Wd)
    ax.set_ylim(0, Hd)
    ax.axis("off")
    gap = 0.3 * s
    cw = (Wd - gap * (cols - 1)) / cols
    ch = min((Hd - gap * (rows - 1)) / rows, cw * 0.75)
    y_top = Hd - (Hd - (ch * rows + gap * (rows - 1))) / 2
    for k, c in enumerate(cards):
        r, q = divmod(k, cols)
        in_row = min(cols, n - r * cols)
        x_off = (Wd - (cw * in_row + gap * (in_row - 1))) / 2
        x0 = x_off + q * (cw + gap)
        y0 = y_top - (r + 1) * ch - r * gap
        ax.add_patch(FancyBboxPatch((x0 + 0.05 * s, y0 - 0.06 * s), cw, ch,
                                    boxstyle=f"round,pad=0,rounding_size={0.18 * s}",
                                    facecolor="black", alpha=0.18, linewidth=0, zorder=1))
        ax.add_patch(FancyBboxPatch((x0, y0), cw, ch, boxstyle=f"round,pad=0,rounding_size={0.18 * s}",
                                    facecolor=d.card, edgecolor=(d.accent if k == 0 else d.grid_color),
                                    linewidth=(1.8 if k == 0 else 0.8) * s, alpha=1, zorder=2))
        ar = has_arabic(str(c.get("label", "")))
        pad = 0.3 * s
        ha = "right" if ar else "left"
        tx = x0 + cw - pad if ar else x0 + pad
        big = min(40 * s, ch * 72 * 0.28, cw * 72 * 0.16)
        # icon or flag in the opposite top corner
        ix = x0 + pad if ar else x0 + cw - pad
        iy = y0 + ch - pad
        if c.get("flag") and get_flag(c["flag"], "round") is not None:
            from ._draw import to_fig
            sz = min(0.55 * s, ch * 0.28)
            fx, fy = to_fig(ax, ix + (sz / 2 if ar else -sz / 2), iy - sz / 2)
            place_image(ax, get_flag(c["flag"], "round"), fx, fy, sz)
        elif c.get("icon"):
            draw_icon(ax, c["icon"], ix, iy, big * 0.75, d.accent, ha="left" if ar else "right", va="top",
                      zorder=5)
        lab = str(c.get("label", ""))
        ax.text(tx, y0 + ch - pad, shape(wrap(lab, 22)), ha=ha, va="top", fontsize=fr.fs(14),
                fontproperties=font("sans", "bold", lab), color=d.muted_color, zorder=5)
        v = c.get("value")
        vs = fmt(v, c.get("decimals", decimals), c.get("prefix", ""), c.get("suffix", ""),
                 c.get("compact", False)) if isinstance(v, (int, float)) else str(v)
        vy = y0 + ch * 0.47
        ax.text(tx, vy, shape(vs), ha=ha, va="center", fontsize=big,
                fontproperties=font("sans", "heavy", vs), color=d.title_color, zorder=5)
        unit = c.get("unit")
        if unit:
            ax.text(tx, vy - big / 72 * 0.75, shape(unit), ha=ha, va="top", fontsize=fr.fs(12.5),
                    fontproperties=font("sans", "regular", unit), color=d.subtitle_color, zorder=5)
        chg = c.get("change")
        note = c.get("note")
        if chg is not None:
            up = chg >= 0
            good = up if c.get("higher_is_better", True) else not up
            col = d.positive if good else d.negative
            txt = f"{'▲' if up else '▼'} {abs(chg):.1f}%"
            if note:
                txt += f"   {note}" if not ar else ""
            ax.text(tx, y0 + pad * 0.9, shape(txt), ha=ha, va="bottom", fontsize=fr.fs(13.5),
                    fontproperties=font("sans", "bold"), color=col, zorder=5)
        elif note:
            ax.text(tx, y0 + pad * 0.9, shape(note), ha=ha, va="bottom", fontsize=fr.fs(12.5),
                    fontproperties=font("sans", "regular", note), color=d.muted_color, zorder=5)
    return fr.finish()
