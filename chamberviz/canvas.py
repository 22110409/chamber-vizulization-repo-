"""The frame shared by every chart: background, faint map, title block, logo, source."""
from __future__ import annotations

import difflib
import io
import json
from functools import lru_cache
from pathlib import Path

import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams["figure.max_open_warning"] = 0
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, to_rgba  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402

from . import config  # noqa: E402
from .assets_lookup import load_image  # noqa: E402
from .text import font, has_arabic, shape  # noqa: E402
from .themes import Design, get_design  # noqa: E402

# Every chart function accepts these keyword arguments.
COMMON_OPTIONS = {
    "figure_size": "(width, height) in inches, e.g. (12, 8)",
    "figsize": "same as figure_size",
    "design": "navy_gold, royal_blue, ivory_dots, emerald_gold, desert_sand, minimal, charcoal_teal",
    "title": "main title", "subtitle": "second line under the title",
    "source": "small text at the bottom, e.g. 'Source: Central Bank'",
    "background_color": "one colour '#123456' or a gradient ('#top', '#bottom')",
    "background_image": "path to a JPG/PNG shown behind the chart",
    "background_image_opacity": "0-1, how strongly the image shows (default 0.35)",
    "background_map": "'solid', 'dots' or False (default: the design's choice)",
    "map_color": "colour of the background map",
    "logo": "'default' (your saved logo), None, a path, or a list of paths",
    "logo_alignment": "'top-right', 'top-left', 'bottom-right', 'bottom-left' (or a tuple like ('top','right'))",
    "logo_size": "logo height as a fraction of the figure height (default 0.10)",
    "title_alignment": "'center', 'left' or 'right'",
    "title_color": "override the design's title colour",
    "title_size": "title font size in points (default scales with the figure)",
    "font_scale": "multiply every font size, e.g. 1.2",
    "save": "file name to save to (.png, .jpg, .svg, .pdf)",
    "dpi": "resolution when saving (default 200)",
    "transparent": "save with a transparent background",
}


# Other spellings people naturally type -> the official option name
ALIASES = {"sub_title": "subtitle", "subTitle": "subtitle", "size": "figure_size",
           "fig_size": "figure_size", "logo_align": "logo_alignment", "logo_position": "logo_alignment",
           "logo_pos": "logo_alignment", "bg_color": "background_color", "background": "background_color",
           "bg_image": "background_image", "background_opacity": "background_image_opacity",
           "theme": "design", "style": "design", "source_text": "source", "map": "background_map"}


def check_options(kwargs: dict, allowed: set, where: str) -> None:
    for a, real in ALIASES.items():
        if a in kwargs and a not in allowed:
            kwargs[real] = kwargs.pop(a)
    for k in kwargs:
        if k not in allowed:
            hint = difflib.get_close_matches(k, sorted(allowed), n=3)
            raise TypeError(f"{where}() got an unknown option '{k}'."
                            + (f" Did you mean: {', '.join(hint)}?" if hint else ""))


def _norm_alignment(a) -> str:
    if isinstance(a, (tuple, list)):
        a = "-".join(str(x) for x in a)
    a = str(a).lower().replace("_", "-").replace(" ", "-").replace(",", "-")
    a = a.replace("down", "bottom").replace("up", "top")
    parts = [p for p in a.split("-") if p]
    v = "bottom" if "bottom" in parts else "top"
    h = "left" if "left" in parts else ("center" if "center" in parts else "right")
    return f"{v}-{h}"


def _gradient(ax, extent, c_bottom, c_top, horizontal=False, zorder=0, alpha=1.0):
    cmap = LinearSegmentedColormap.from_list("g", [c_bottom, c_top])
    arr = np.linspace(0, 1, 256).reshape(1, -1) if horizontal else np.linspace(0, 1, 256).reshape(-1, 1)
    return ax.imshow(arr, aspect="auto", cmap=cmap, origin="lower", extent=extent,
                     zorder=zorder, alpha=alpha, interpolation="bicubic")


# ---------------------------------------------------------------- map data
@lru_cache(maxsize=4)
def _land_paths():
    data = json.loads((config.MAPS_DIR / "world_land_110m.geojson").read_text())
    out = []
    for f in data["features"]:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        out += [np.asarray(p[0]) for p in polys]
    return out


@lru_cache(maxsize=8)
def _land_dots(step: float):
    lon, lat = np.meshgrid(np.arange(-180, 180, step), np.arange(-58, 84, step))
    pts = np.column_stack([lon.ravel(), lat.ravel()])
    inside = np.zeros(len(pts), bool)
    for ring in _land_paths():
        inside |= MplPath(ring).contains_points(pts)
    return pts[inside]


class Frame:
    """Creates the figure and draws everything that is not the chart itself."""

    def __init__(self, where: str, extra_allowed: set = frozenset(), **kw):
        check_options(kw, set(COMMON_OPTIONS) | set(extra_allowed), where)
        self.kw = kw
        d = config.DEFAULTS
        self.design: Design = get_design(kw.get("design", d["design"]))
        size = kw.get("figure_size", kw.get("figsize", d["figure_size"]))
        self.W, self.H = float(size[0]), float(size[1])
        s = float(np.sqrt((self.W / 16) * (self.H / 9)))
        self.s = float(np.clip(s, 0.55, 1.6)) * float(kw.get("font_scale", 1.0))
        self.fig = plt.figure(figsize=(self.W, self.H), dpi=100)
        bg = kw.get("background_color")
        if bg is None:
            self.bg = tuple(self.design.background)
        elif isinstance(bg, (tuple, list)):
            self.bg = (bg[0], bg[1])
        else:
            self.bg = (bg, bg)
        self.fig.patch.set_facecolor(self.bg[1])
        self._draw_background()
        self._layout_header_footer()

    # ------------------------------------------------------------ helpers
    def fs(self, pt: float) -> float:
        """Scale a font size (points) to the figure."""
        return pt * self.s

    def inch_x(self, v):
        return v / self.W

    def inch_y(self, v):
        return v / self.H

    @property
    def is_dark(self) -> bool:
        r, g, b, _ = to_rgba(self.bg[1])
        return (0.299 * r + 0.587 * g + 0.114 * b) < 0.5

    # ------------------------------------------------------------ background
    def _draw_background(self):
        ax = self.fig.add_axes([0, 0, 1, 1], zorder=-20)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        _gradient(ax, [0, 1, 0, 1], self.bg[1], self.bg[0], zorder=0)
        img_path = self.kw.get("background_image")
        if img_path:
            img = load_image(img_path)
            h, w = img.shape[:2]
            target = self.W / self.H
            if w / h > target:  # crop width ("cover" fit)
                nw = int(h * target)
                x0 = (w - nw) // 2
                img = img[:, x0:x0 + nw]
            else:
                nh = int(w / target)
                y0 = (h - nh) // 2
                img = img[y0:y0 + nh]
            ax.imshow(img, extent=[0, 1, 0, 1], aspect="auto", zorder=1,
                      alpha=float(self.kw.get("background_image_opacity", 0.35)))
        self.bg_ax = ax

    def draw_map(self, rect):
        style = self.kw.get("background_map", None)
        if style is None:
            style = self.design.map_style
        if style in (False, "none", None):
            return
        color = self.kw.get("map_color", self.design.map_color)
        ax = self.fig.add_axes(rect, zorder=-10)
        ax.set_xlim(-170, 190)
        ax.set_ylim(-58, 84)
        ax.axis("off")
        if style == "dots":
            step = 1.6 if self.W >= 12 else 2.0
            pts = _land_dots(step)
            size = 6 * (self.W / 16) ** 2 * (1.6 / step) ** -2
            ax.scatter(pts[:, 0], pts[:, 1], s=size, marker="s", color=color,
                       alpha=self.design.map_alpha, linewidths=0)
        else:
            for ring in _land_paths():
                ax.add_patch(Polygon(ring, closed=True, facecolor=color, edgecolor="none",
                                     alpha=self.design.map_alpha))

    # ------------------------------------------------------------ header/footer
    def _logos(self):
        logo = self.kw.get("logo", config.DEFAULTS["logo"])
        align = self.kw.get("logo_alignment", config.DEFAULTS["logo_alignment"])
        if logo in (None, False, ""):
            return []
        logos = logo if isinstance(logo, (list, tuple)) and not isinstance(logo, str) else [logo]
        aligns = align if isinstance(align, list) else [align] * len(logos)
        out = []
        for lg, al in zip(logos, aligns):
            if lg == "default":
                lg = config.default_logo_path()
                if lg is None:
                    continue
            p = Path(lg)
            if not p.exists():
                raise FileNotFoundError(f"Logo not found: {p}")
            if p.suffix.lower() == ".svg":
                raise ValueError("Please give the logo as PNG or JPG (SVG is not supported).")
            out.append((load_image(p), _norm_alignment(al)))
        return out

    def _layout_header_footer(self):
        kw, d, s = self.kw, self.design, self.s
        self.margin = 0.35 * s
        title, subtitle = kw.get("title"), kw.get("subtitle")
        y = 0.38 * s  # inches from the top
        self.title_size = kw.get("title_size") or self.fs(30)
        self.title_y = self.subtitle_y = self.accent_y = None
        if title:
            lines = str(title).count("\n") + 1
            h = self.title_size / 72 * 1.25 * lines
            self.title_y = y + h / 2
            y += h + 0.08 * s
        if subtitle:
            h = self.fs(15) / 72 * 1.3 * (str(subtitle).count("\n") + 1)
            self.subtitle_y = y + h / 2
            y += h + 0.06 * s
        if title:
            self.accent_y = y + 0.06 * s
            y += 0.2 * s
        logos = self._logos()
        lh = float(kw.get("logo_size", config.DEFAULTS["logo_size"])) * self.H
        self.logos = logos
        self.logo_h = lh
        top_logo = any(a.startswith("top") for _, a in logos)
        bottom_logo = any(a.startswith("bottom") for _, a in logos)
        if top_logo:
            y = max(y, self.margin * 0.6 + lh + 0.05 * s)
        self.header_h = y + 0.25 * s
        foot = 0.3 * s
        if kw.get("source"):
            foot = max(foot, 0.6 * s)
        if bottom_logo:
            foot = max(foot, lh + self.margin * 0.9)
        self.footer_h = foot

    def plot_rect(self, left=0.9, right=0.4, bottom=0.8, top=0.2, square=False):
        """Axes rectangle (figure fractions) after reserving space in inches."""
        l, r = left * self.s, right * self.s
        b, t = self.footer_h + bottom * self.s, self.header_h + top * self.s
        w, h = self.W - l - r, self.H - b - t
        if square:
            side = min(w, h)
            l += (w - side) / 2
            w = h = side
        return [l / self.W, b / self.H, max(w, 0.5) / self.W, max(h, 0.5) / self.H]

    def content_rect(self):
        """Area between header and footer (used for the background map)."""
        b = self.footer_h / self.H
        t = 1 - (self.header_h - 0.1 * self.s) / self.H
        return [0.03, b, 0.94, max(t - b, 0.1)]

    def finish(self):
        kw, d, fig = self.kw, self.design, self.fig
        self.draw_map(self.content_rect())
        align = kw.get("title_alignment", "center")
        logo_sides = {a for _, a in self.logos if a.startswith("top")}
        pad = self.margin
        xs = {"center": 0.5, "left": pad / self.W, "right": 1 - pad / self.W}
        if align != "center" and f"top-{align}" in logo_sides:
            lw = self.logo_h * 2.2
            xs["left"] += lw / self.W
            xs["right"] -= lw / self.W
        x = xs.get(align, 0.5)
        ha = {"center": "center", "left": "left", "right": "right"}[align]
        title, subtitle = kw.get("title"), kw.get("subtitle")
        if title:
            fig.text(x, 1 - self.title_y / self.H, shape(title), ha=ha, va="center",
                     fontproperties=font(d.title_font, "bold", title), fontsize=self.title_size,
                     color=kw.get("title_color", d.title_color))
        if subtitle:
            fig.text(x, 1 - self.subtitle_y / self.H, shape(subtitle), ha=ha, va="center",
                     fontproperties=font("sans", "regular", subtitle), fontsize=self.fs(15),
                     color=d.subtitle_color)
        if title:
            lw_in = min(2.6 * self.s, self.W * 0.25)
            x0 = {"center": x - lw_in / 2 / self.W, "left": x, "right": x - lw_in / self.W}[ha]
            lax = fig.add_axes([x0, 1 - self.accent_y / self.H - 0.003, lw_in / self.W, 0.006 * self.s],
                               zorder=5)
            fade = 1 - np.abs(np.linspace(-1, 1, 300)) ** 3 if ha == "center" else \
                (np.linspace(1, 0, 300) if ha == "left" else np.linspace(0, 1, 300))
            rgba = np.zeros((1, 300, 4))
            rgba[..., :3] = to_rgba(d.accent)[:3]
            rgba[..., 3] = fade
            lax.imshow(rgba, aspect="auto")
            lax.axis("off")
        # logos
        for img, a in self.logos:
            h, w = img.shape[:2]
            lh = self.logo_h
            lw = lh * w / h
            v, hz = a.split("-")
            m = self.margin * 0.8
            x0 = m if hz == "left" else (self.W - m - lw if hz == "right" else (self.W - lw) / 2)
            y0 = self.H - m * 0.75 - lh if v == "top" else m * 0.6
            lax = fig.add_axes([x0 / self.W, y0 / self.H, lw / self.W, lh / self.H], zorder=6)
            lax.imshow(img, interpolation="antialiased")
            lax.axis("off")
        # source
        src = kw.get("source")
        if src:
            bottom_sides = {a.split("-")[1] for _, a in self.logos if a.startswith("bottom")}
            if not bottom_sides:
                sx, sha = 0.5, "center"
            elif "right" in bottom_sides:
                sx, sha = pad / self.W, "left"
            else:
                sx, sha = 1 - pad / self.W, "right"
            fig.text(sx, (0.32 * self.s) / self.H, shape(src), ha=sha, va="center",
                     fontproperties=font("sans", "regular", src), fontsize=self.fs(11.5),
                     color=d.muted_color)
        chart = Chart(fig, self)
        if kw.get("save"):
            chart.save(kw["save"])
        return chart


class Chart:
    """What every chart function returns. Use .save('file.png') or .show()."""

    def __init__(self, fig, frame: Frame):
        self.fig = fig
        self.frame = frame

    def save(self, path, dpi=None, transparent=None):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tr = self.frame.kw.get("transparent", False) if transparent is None else transparent
        self.fig.savefig(path, dpi=dpi or self.frame.kw.get("dpi", config.DEFAULTS["dpi"]),
                         facecolor="none" if tr else self.fig.get_facecolor(), transparent=tr)
        return path

    def to_bytes(self, fmt="png", dpi=None) -> bytes:
        buf = io.BytesIO()
        self.fig.savefig(buf, format=fmt, dpi=dpi or config.DEFAULTS["dpi"],
                         facecolor=self.fig.get_facecolor())
        return buf.getvalue()

    def show(self):
        plt.show()

    def close(self):
        plt.close(self.fig)

    def _repr_png_(self):
        return self.to_bytes(dpi=100)
