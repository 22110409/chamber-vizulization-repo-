"""Low-level drawing helpers shared by the chart functions."""
from __future__ import annotations

import numpy as np
from matplotlib.colors import LinearSegmentedColormap, to_rgba
from matplotlib.patches import FancyBboxPatch, Rectangle

from .assets_lookup import auto_icon, country_code, flag, icon_char, looks_like_countries
from .text import icon_font


# ---------------------------------------------------------------- data input
def xy(data=None, values=None, x=None, y=None, where="chart"):
    """Accept (labels, values) lists, a dict, a pandas Series or a DataFrame + column names."""
    try:
        import pandas as pd
    except Exception:  # pragma: no cover
        pd = None
    if pd is not None and isinstance(data, pd.DataFrame):
        if x is None or y is None:
            cols = list(data.columns)
            num = [c for c in cols if pd.api.types.is_numeric_dtype(data[c])]
            txt = [c for c in cols if c not in num]
            x = x if x is not None else (txt[0] if txt else cols[0])
            y = y if y is not None else (num[0] if num else cols[1])
        return [v for v in data[x].tolist()], [float(v) for v in data[y].tolist()]
    if pd is not None and isinstance(data, pd.Series):
        return list(data.index), [float(v) for v in data.values]
    if isinstance(data, dict):
        return list(data.keys()), [float(v) for v in data.values()]
    if data is not None and values is not None:
        return list(data), [float(v) for v in values]
    raise TypeError(f"{where}(): give labels and values, a dict, or a DataFrame with x= and y=")


def series_input(data=None, x=None, y=None):
    """Multi-series: returns (x_labels, {name: values})."""
    import pandas as pd
    if isinstance(data, pd.DataFrame):
        if x is None:
            x = data.columns[0]
        ys = y if isinstance(y, (list, tuple)) else ([y] if y else
                                                     [c for c in data.columns if c != x and pd.api.types.is_numeric_dtype(data[c])])
        return data[x].tolist(), {str(c): [float(v) for v in data[c].tolist()] for c in ys}
    raise TypeError("expected a DataFrame")


# ---------------------------------------------------------------- geometry
def px_scale(ax):
    """Pixels per data unit on x and y (axes must already have limits)."""
    fig = ax.figure
    bb = ax.get_position()
    w_px = bb.width * fig.get_figwidth() * fig.dpi
    h_px = bb.height * fig.get_figheight() * fig.dpi
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    return w_px / abs(x1 - x0), h_px / abs(y1 - y0)


def to_fig(ax, x, y, dx_in=0.0, dy_in=0.0, ycoord="data", xcoord="data"):
    """Data (or axes-fraction) point + offset in inches -> figure fraction."""
    fig = ax.figure
    bb = ax.get_position()
    if xcoord == "axes":
        fx = bb.x0 + x * bb.width
    else:
        fx = fig.transFigure.inverted().transform(ax.transData.transform((x, ax.get_ylim()[0])))[0]
    if ycoord == "axes":
        fy = bb.y0 + y * bb.height
    else:
        fy = fig.transFigure.inverted().transform(ax.transData.transform((ax.get_xlim()[0], y)))[1]
    return fx + dx_in / fig.get_figwidth(), fy + dy_in / fig.get_figheight()


def place_image(ax, img, fx, fy, size_in, ring=None, ring_width=1.2, zorder=8):
    """Put an image centred at figure fraction (fx, fy) with width size_in."""
    if img is None:
        return None
    fig = ax.figure
    h, w = img.shape[:2]
    wi, hi = size_in, size_in * h / w
    iax = fig.add_axes([fx - wi / 2 / fig.get_figwidth(), fy - hi / 2 / fig.get_figheight(),
                        wi / fig.get_figwidth(), hi / fig.get_figheight()], zorder=zorder)
    iax.imshow(img, interpolation="antialiased")
    iax.set_xlim(-0.5, w - 0.5)
    iax.set_ylim(h - 0.5, -0.5)
    iax.axis("off")
    if ring:
        from matplotlib.patches import Circle
        iax.add_patch(Circle(((w - 1) / 2, (h - 1) / 2), w / 2 - 0.5, fill=False,
                             edgecolor=ring, linewidth=ring_width))
    return iax


def resolve_flags(labels, flags):
    """flags='auto' | True | False | list of countries -> list of country names or None."""
    if flags is None or flags is False:
        return None
    if isinstance(flags, (list, tuple)):
        return list(flags)
    if flags == "auto":
        return list(labels) if looks_like_countries(labels) else None
    return list(labels)


def resolve_icons(labels, icons):
    if not icons:
        return None
    if isinstance(icons, (list, tuple)):
        return list(icons)
    if isinstance(icons, dict):
        return [icons.get(l) for l in labels]
    if icons == "auto":
        return [auto_icon(l) for l in labels]
    if isinstance(icons, str):
        return [icons] * len(labels)
    return None


def get_flag(country, style):
    return flag(country, style) if country_code(country) else None


def draw_icon(ax, name, x, y, size_pt, color, variant="outline", dx_pt=0, dy_pt=0,
              zorder=6, xycoords="data", ha="center", va="center"):
    if not name:
        return None
    ch = icon_char(name, variant)
    return ax.annotate(ch, (x, y), xycoords=xycoords, xytext=(dx_pt, dy_pt),
                       textcoords="offset points", ha=ha, va=va,
                       fontproperties=icon_font(variant), fontsize=size_pt, color=color,
                       zorder=zorder, annotation_clip=False)


# ---------------------------------------------------------------- bars
def _as_grad(c):
    if isinstance(c, (tuple, list)) and len(c) == 2 and not isinstance(c[0], (int, float)):
        return c[0], c[1]
    return c, c


def bar(ax, pos, length, width, grad, base=0.0, horizontal=False, radius_px=0.0,
        cap=None, cap_width=2.0, shadow=False, glow=None, zorder=3, edge=None, outline=True):
    """Draw one gradient bar. pos = centre on the category axis."""
    c0, c1 = _as_grad(grad)
    neg = length < 0
    a, b = (base + length, base) if neg else (base, base + length)
    if horizontal:
        x0, x1, y0, y1 = a, b, pos - width / 2, pos + width / 2
    else:
        x0, x1, y0, y1 = pos - width / 2, pos + width / 2, a, b
    if x1 - x0 <= 0 or y1 - y0 <= 0:
        return
    sx, sy = px_scale(ax)
    w_px, h_px = (x1 - x0) * sx, (y1 - y0) * sy
    r_px = min(radius_px, w_px / 2.2, h_px / 2.2)
    if r_px > 0.5:
        style = f"round,pad=0,rounding_size={r_px / sx}"
        mut = sx / sy
    else:
        style, mut = "square,pad=0", 1
    if glow:
        for k, al in enumerate(np.linspace(0.10, 0.01, 8)):
            pad = (k + 1) * 3.0
            ax.add_patch(Rectangle((x0 - pad / sx, y0), (x1 - x0) + 2 * pad / sx,
                                   (y1 - y0) + (pad * 1.2) / sy, color=glow, alpha=al,
                                   linewidth=0, zorder=zorder - 2))
    if shadow:
        ax.add_patch(FancyBboxPatch((x0 + 5 / sx, y0 - (0 if not horizontal else 5 / sy)),
                                    x1 - x0, (y1 - y0) - (4 / sy if not horizontal else 0),
                                    boxstyle=style, mutation_aspect=mut, facecolor="black",
                                    alpha=0.12, linewidth=0, zorder=zorder - 1))
    clip = FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle=style, mutation_aspect=mut,
                          facecolor="none", edgecolor=edge or (1, 1, 1, 0.13 if outline else 0),
                          linewidth=1.0, zorder=zorder + 0.5)
    ax.add_patch(clip)
    cmap = LinearSegmentedColormap.from_list("b", [c0, c1])
    if horizontal:
        arr = np.linspace(0, 1, 256).reshape(1, -1)
        if neg:
            arr = arr[:, ::-1]
    else:
        arr = np.linspace(0, 1, 256).reshape(-1, 1)
        if neg:
            arr = arr[::-1]
    img = ax.imshow(arr, aspect="auto", cmap=cmap, origin="lower", extent=[x0, x1, y0, y1],
                    zorder=zorder, interpolation="bicubic")
    img.set_clip_path(clip)
    if cap:
        if horizontal:
            e = x0 if neg else x1
            ax.plot([e, e], [y0, y1], color=cap, linewidth=cap_width, zorder=zorder + 1,
                    solid_capstyle="butt")
        else:
            e = y0 if neg else y1
            ax.plot([x0, x1], [e, e], color=cap, linewidth=cap_width, zorder=zorder + 1,
                    solid_capstyle="butt")


def style_axes(ax, frame, grid="y", show_axis=True, baseline=True, baseline_side=None):
    d = frame.design
    ax.set_facecolor("none")
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    if baseline:
        sp = baseline_side or ("left" if grid == "x" else "bottom")
        ax.spines[sp].set_visible(True)
        ax.spines[sp].set_color(d.axis_color)
        ax.spines[sp].set_linewidth(1.4 * frame.s)
    if grid:
        ax.grid(axis=grid, color=d.grid_color, alpha=d.grid_alpha, linewidth=0.9)
        ax.set_axisbelow(True)
    ax.tick_params(colors=d.muted_color, labelsize=frame.fs(12), length=0, pad=6 * frame.s)
    for lab in ax.get_xticklabels() + ax.get_yticklabels():
        lab.set_color(d.muted_color)
    if not show_axis:
        if grid == "x":
            ax.set_xticklabels([])
        else:
            ax.set_yticklabels([])


def rgba(c, a):
    r, g, b, _ = to_rgba(c)
    return (r, g, b, a)


def text_color_on(c) -> str:
    r, g, b, _ = to_rgba(c)
    return "#111111" if (0.299 * r + 0.587 * g + 0.114 * b) > 0.6 else "#ffffff"


class LabelPlacer:
    """Remembers occupied screen areas so labels do not overlap."""

    def __init__(self, fig, pad_px=3):
        self.fig = fig
        self.boxes = []
        self.pad = pad_px
        self.r = fig.canvas.get_renderer()

    def _hit(self, bb):
        p = self.pad
        for b in self.boxes:
            if not (bb.x1 + p < b.x0 or bb.x0 - p > b.x1 or bb.y1 + p < b.y0 or bb.y0 - p > b.y1):
                return True
        return False

    def reserve_fig_rect(self, fx, fy, w_in, h_in):
        """Reserve a box centred at figure fraction (fx, fy) with size in inches."""
        from matplotlib.transforms import Bbox
        dpi = self.fig.dpi
        cx, cy = fx * self.fig.get_figwidth() * dpi, fy * self.fig.get_figheight() * dpi
        bb = Bbox.from_extents(cx - w_in * dpi / 2, cy - h_in * dpi / 2, cx + w_in * dpi / 2, cy + h_in * dpi / 2)
        self.boxes.append(bb)
        return bb

    def fits_fig_rect(self, fx, fy, w_in, h_in):
        from matplotlib.transforms import Bbox
        dpi = self.fig.dpi
        cx, cy = fx * self.fig.get_figwidth() * dpi, fy * self.fig.get_figheight() * dpi
        return not self._hit(Bbox.from_extents(cx - w_in * dpi / 2, cy - h_in * dpi / 2,
                                               cx + w_in * dpi / 2, cy + h_in * dpi / 2))

    def try_text(self, artist, positions=None):
        """Keep the text if it fits (optionally trying other offsets), else remove it."""
        cands = positions or [None]
        for pos in cands:
            if pos is not None:
                artist.set_position(pos[0])
                artist.set_ha(pos[1])
                if len(pos) > 2:
                    artist.set_va(pos[2])
            bb = artist.get_window_extent(renderer=self.r)
            if not self._hit(bb):
                self.boxes.append(bb)
                return True
        artist.remove()
        return False


def lum(c) -> float:
    r, g, b, _ = to_rgba(c)
    return 0.299 * r + 0.587 * g + 0.114 * b


def readable_on(color, background) -> str:
    """Return `color`, or black/white if it would be hard to see on `background`."""
    return color if abs(lum(color) - lum(background)) >= 0.28 else text_color_on(background)
