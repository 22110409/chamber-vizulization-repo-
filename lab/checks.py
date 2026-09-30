"""Automatic checks on a rendered chart: things a person might miss at a glance.

* text cut off at the edge of the image
* text that overlaps other text (labels colliding)
* render time and errors are recorded by the caller
"""
from __future__ import annotations

from matplotlib.text import Text

_ICON_FONTS = ("tabler",)


def _hidden_ticks(fig) -> set:
    """Tick labels outside an axis' visible range: matplotlib keeps them but never draws them."""
    hidden = set()
    for ax in fig.axes:
        for axis, (low, high) in ((ax.xaxis, ax.get_xlim()), (ax.yaxis, ax.get_ylim())):
            low, high = min(low, high), max(low, high)
            span = (high - low) * 1e-9
            for tick in axis.get_major_ticks() + axis.get_minor_ticks():
                if not low - span <= tick.get_loc() <= high + span:
                    hidden.update({id(tick.label1), id(tick.label2)})
    return hidden


def _texts(fig):
    renderer = fig.canvas.get_renderer()
    hidden = _hidden_ticks(fig)
    out = []
    for t in fig.findobj(Text):
        if id(t) in hidden or not t.get_visible() or not t.get_text().strip():
            continue
        if any(name in (t.get_fontname() or "").lower() for name in _ICON_FONTS):
            continue  # icon glyphs are drawn as text; they are not labels
        try:
            box = t.get_window_extent(renderer)
        except Exception:  # pragma: no cover - artists without a renderer
            continue
        if box.width > 0 and box.height > 0:
            out.append((t.get_text().replace("\n", " ")[:40], box))
    return out


def check(fig, margin: float = 2.0, overlap_share: float = 0.3) -> list[str]:
    """Return human-readable warnings (empty list = nothing found)."""
    fig.canvas.draw()
    frame = fig.bbox
    texts = _texts(fig)
    warnings = []

    cut = [text for text, box in texts
           if box.x0 < frame.x0 - margin or box.x1 > frame.x1 + margin
           or box.y0 < frame.y0 - margin or box.y1 > frame.y1 + margin]
    if cut:
        warnings.append(f"text cut off at the edge: {', '.join(repr(c) for c in cut[:3])}")

    collisions = []
    for i in range(len(texts)):
        a_text, a = texts[i]
        for b_text, b in texts[i + 1:]:
            if a_text == b_text:
                continue
            w = min(a.x1, b.x1) - max(a.x0, b.x0)
            h = min(a.y1, b.y1) - max(a.y0, b.y0)
            if w <= 0 or h <= 0:
                continue
            # Text boxes include the font's full line height (tall for Arabic fonts), so lines
            # stacked closely touch without the letters meeting. Real collisions overlap across
            # most of the height of the smaller label.
            if h < 0.5 * min(a.height, b.height):
                continue
            smaller = min(a.width * a.height, b.width * b.height)
            if smaller and (w * h) / smaller > overlap_share:
                collisions.append(f"{a_text!r} / {b_text!r}")
    if collisions:
        warnings.append(f"{len(collisions)} overlapping label(s), e.g. {collisions[0]}")
    return warnings
