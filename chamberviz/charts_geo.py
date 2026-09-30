"""Geo charts: choropleth / bubble maps and trade-flow maps (arcs into Jordan)."""
from __future__ import annotations

import json
import warnings
from functools import lru_cache

import numpy as np
from matplotlib import patheffects
from matplotlib.colors import LinearSegmentedColormap, LogNorm, Normalize
from matplotlib.patches import Polygon

from . import config
from ._draw import get_flag, place_image, rgba, to_fig, xy
from .assets_lookup import country_code, country_info
from .canvas import Frame
from .charts_bar import VALUE_OPTS, _vfmt
from .text import fmt, font, has_arabic, shape

REGIONS = {
    "world": (-170, 190, -56, 80),
    "middle_east": (24, 64, 11, 43),
    "mena": (-18, 64, 8, 44),
    "arab_world": (-18, 62, -3, 40),
    "gcc": (34, 60, 12, 32),
    "levant": (31, 44, 28, 38.5),
    "europe": (-25, 45, 34, 71),
    "asia": (25, 150, -12, 60),
    "africa": (-20, 55, -36, 38),
    "americas": (-170, -30, -56, 75),
}


@lru_cache(maxsize=2)
def _countries(res: str):
    data = json.loads((config.MAPS_DIR / f"world_countries_{res}.geojson").read_text())
    out = []
    for f in data["features"]:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        out.append((f["properties"]["iso2"], [np.asarray(p[0]) for p in polys]))
    return out


def _region_box(region, codes):
    if isinstance(region, (tuple, list)):
        return tuple(region)
    if region != "auto":
        if region not in REGIONS:
            raise ValueError(f"Unknown region '{region}'. Use one of {', '.join(REGIONS)} or (lon0, lon1, lat0, lat1)")
        return REGIONS[region]
    pts = [(country_info(c)["lon"], country_info(c)["lat"]) for c in codes
           if country_info(c) and country_info(c)["lon"] is not None]
    if not pts:
        return REGIONS["world"]
    lon, lat = zip(*pts)
    if max(lon) - min(lon) > 110 or max(lat) - min(lat) > 70:
        return REGIONS["world"]
    pad = max(6, (max(lon) - min(lon)) * 0.25)
    return (min(lon) - pad, max(lon) + pad, min(lat) - pad * 0.7, max(lat) + pad * 0.7)


def _base_map(fr, ax, box, land, border, fills=None, lw=0.5):
    res = "110m" if (box[1] - box[0]) > 120 else "50m"
    for code, rings in _countries(res):
        fc = (fills or {}).get(code, land)
        for r in rings:
            if r[:, 0].max() < box[0] - 30 or r[:, 0].min() > box[1] + 30:
                continue
            ax.add_patch(Polygon(r, closed=True, facecolor=fc, edgecolor=border,
                                 linewidth=lw * fr.s, zorder=2 if code in (fills or {}) else 1))


def _fit_box(box, w_in, h_in):
    """Grow the lon or lat range so the map fills the rectangle without distortion."""
    x0, x1, y0, y1 = box
    k = max(np.cos(np.deg2rad((y0 + y1) / 2)), 0.3)
    want = w_in / h_in
    have = (x1 - x0) * k / (y1 - y0)
    if have < want:
        extra = ((y1 - y0) * want / k - (x1 - x0)) / 2
        x0, x1 = x0 - extra, x1 + extra
    else:
        extra = ((x1 - x0) * k / want - (y1 - y0)) / 2
        y0, y1 = y0 - extra, y1 + extra
        # never show Antarctica / the empty far north: shift, clamp, then widen instead
        if y0 < -58 and y1 < 84:
            y1, y0 = min(84, y1 + (-58 - y0)), -58
        if y1 > 84:
            y0, y1 = max(-58, y0 - (y1 - 84)), 84
    return x0, x1, y0, y1


def _map_axes(fr, box, bottom=0.25, right=0.3):
    rect = fr.plot_rect(left=0.3, right=right, bottom=bottom, top=0.1)
    ax = fr.fig.add_axes(rect)
    box = _fit_box(box, rect[2] * fr.W, rect[3] * fr.H)
    ax.set_xlim(box[0], box[1])
    ax.set_ylim(box[2], box[3])
    k = max(np.cos(np.deg2rad((box[2] + box[3]) / 2)), 0.3)
    ax.set_aspect(1 / k, adjustable="box", anchor="C")
    ax.apply_aspect()  # fix the final position now, so flags land in the right place
    ax.set_position(ax.get_position(original=False))
    ax.axis("off")
    return ax, box


def _halo(fr, color):
    return [patheffects.withStroke(linewidth=3.2 * fr.s, foreground=color)]


def geoplot(data=None, values=None, *, x=None, y=None, region="auto", style="choropleth",
            label_top=8, show_flags=True, scale="linear", colors=None, highlight=None,
            legend_title=None, bubble_color=None, **kw):
    """World or regional map coloured by value per country.

    geoplot(["Saudi Arabia", "China", "USA"], [2975, 4180, 1692], region="world")
    style  : "choropleth" (fill countries) or "bubbles" (circles sized by value)
    region : "auto", "world", "middle_east", "mena", "arab_world", "gcc", "levant",
             "europe", "asia", "africa", "americas" or (lon_min, lon_max, lat_min, lat_max)
    """
    opts = {k: kw.pop(k) for k in list(kw) if k in VALUE_OPTS}
    kw.setdefault("background_map", False)
    fr = Frame("geoplot", **kw)
    d, s = fr.design, fr.s
    labels, vals = xy(data, values, x, y, "geoplot")
    codes, v2, missing, names2 = [], [], [], []
    for l, v in zip(labels, vals):
        c = country_code(l)
        if c:
            codes.append(c)
            v2.append(v)
            names2.append(str(l))
        else:
            missing.append(l)
    if missing:
        warnings.warn(f"geoplot: could not match these to countries: {missing}")
    vf = _vfmt(opts, v2)
    box = _region_box(region, codes)
    ax, box = _map_axes(fr, box, bottom=0.55)
    cmap = LinearSegmentedColormap.from_list("seq", list(colors or d.sequential))
    vmin, vmax = min(v2), max(v2)
    norm = LogNorm(max(vmin, 1e-9), vmax) if scale == "log" else Normalize(min(0, vmin), vmax)
    fills = {}
    if style == "choropleth":
        fills = {c: cmap(norm(v)) for c, v in zip(codes, v2)}
    hl = country_code(highlight) if highlight else None
    if hl:
        fills[hl] = d.accent
    _base_map(fr, ax, box, d.land_color, d.border_color, fills)
    order = np.argsort(v2)[::-1]
    if style == "bubbles":
        bc = bubble_color or d.accent
        for i in order[::-1]:
            info = country_info(codes[i])
            if not info or info["lon"] is None:
                continue
            area = 80 + 2600 * (v2[i] / vmax) if vmax > 0 else 80
            ax.scatter([info["lon"]], [info["lat"]], s=area * s ** 2, color=rgba(bc, 0.55),
                       edgecolor=bc, linewidth=1.5 * s, zorder=5)
    # labels on the biggest countries (skipped when they would overlap)
    from ._draw import LabelPlacer
    lp = LabelPlacer(fr.fig)
    arabic = any(has_arabic(l) for l in labels)
    fsz = 0.26 * s
    for rank, i in enumerate(order[:label_top]):
        info = country_info(codes[i])
        if not info or info["lon"] is None:
            continue
        lon, lat = info["lon"], info["lat"]
        if not (box[0] <= lon <= box[1] and box[2] <= lat <= box[3]):
            continue
        name = info["ar"] if arabic else (info["en"] if len(info["en"]) <= 16 else names2[i])
        img = get_flag(codes[i], "round") if show_flags else None
        fx, fy = to_fig(ax, lon, lat)
        if img is not None and not lp.fits_fig_rect(fx, fy + fsz * 0.55 / fr.H, fsz, fsz):
            img = None
        t = ax.annotate(f"{shape(name)}\n{vf(v2[i])}", (lon, lat),
                        xytext=(0, -fsz * 72 * 0.1 if img is not None else 0), textcoords="offset points",
                        ha="center", va="top" if img is not None else "center", fontsize=fr.fs(10.5),
                        fontproperties=font("sans", "bold", name), color=d.text_color, zorder=9,
                        path_effects=_halo(fr, d.surface), linespacing=1.1)
        if lp.try_text(t):
            if img is not None:
                lp.reserve_fig_rect(fx, fy + fsz * 0.55 / fr.H, fsz, fsz)
                place_image(ax, img, fx, fy + fsz * 0.55 / fr.H, fsz, ring=d.surface, ring_width=1.2)
    # colour scale
    if style == "choropleth":
        bb = ax.get_position()
        cax = fr.fig.add_axes([bb.x0 + bb.width * 0.02, (fr.footer_h + 0.28 * s) / fr.H,
                               min(0.25, 3.2 * s / fr.W), 0.012 * s * 16 / fr.H * 0.6])
        grad = np.linspace(0, 1, 256).reshape(1, -1)
        cax.imshow(grad, aspect="auto", cmap=cmap)
        cax.set_xticks([0, 255])
        cax.set_xticklabels([vf(norm.vmin), vf(vmax)])
        cax.set_yticks([])
        cax.tick_params(length=0, labelsize=fr.fs(10.5), colors=d.muted_color, pad=3)
        for sp in cax.spines.values():
            sp.set_visible(False)
        if legend_title:
            cax.set_title(shape(legend_title), fontproperties=font("sans", "bold", legend_title),
                          fontsize=fr.fs(11), color=d.text_color, loc="left", pad=4)
    return fr.finish()


def _bezier(p0, p1, bend=0.25, n=60):
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    mid = (p0 + p1) / 2
    dvec = p1 - p0
    normal = np.array([-dvec[1], dvec[0]])
    ctrl = mid + normal * bend
    t = np.linspace(0, 1, n)[:, None]
    return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * ctrl + t ** 2 * p1


def flowmap(data=None, values=None, *, x=None, y=None, hub="Jordan", direction="in",
            region="auto", top=12, show_flags=True, line_color=None, hub_label=True,
            ranking=True, **kw):
    """Trade-flow map: curved arrows from each partner to the hub (default Jordan),
    with a ranked list of partners (flag, name, value) beside the map.

    flowmap(["China", "Saudi Arabia", "USA"], [4180, 2975, 1692], hub="Jordan")
    direction : "in" (imports: partner -> hub) or "out" (exports: hub -> partner)
    ranking   : show the ranked list on the side (True) or label the map directly (False)
    """
    opts = {k: kw.pop(k) for k in list(kw) if k in VALUE_OPTS}
    kw.setdefault("background_map", False)
    fr = Frame("flowmap", **kw)
    d, s = fr.design, fr.s
    labels, vals = xy(data, values, x, y, "flowmap")
    hub_info = country_info(hub)
    if not hub_info:
        raise ValueError(f"Unknown hub country: {hub}")
    pairs = [(str(l), v, country_info(l)) for l, v in zip(labels, vals)]
    skipped = [p[0] for p in pairs if not (p[2] and p[2]["lon"] is not None)]
    if skipped:
        warnings.warn(f"flowmap: could not match these to countries: {skipped}")
    pairs = [p for p in pairs if p[2] and p[2]["lon"] is not None]
    pairs = sorted(pairs, key=lambda p: -p[1])[:top]
    vf = _vfmt(opts, [p[1] for p in pairs])
    arabic = any(has_arabic(l) for l in labels)
    panel_in = 3.6 * s if ranking else 0
    box = _region_box(region, [p[2]["iso2"] for p in pairs] + [hub_info["iso2"]])
    ax, box = _map_axes(fr, box, right=(0.3 + panel_in / s) if not arabic else 0.3)
    if ranking and arabic:  # panel on the left for Arabic
        bb = ax.get_position()
        ax.set_position([bb.x0 + panel_in / fr.W, bb.y0, bb.width - panel_in / fr.W, bb.height])
        box = _fit_box(box, (bb.width * fr.W - panel_in), bb.height * fr.H)
        ax.set_xlim(box[0], box[1])
        ax.set_ylim(box[2], box[3])
    _base_map(fr, ax, box, d.land_color, d.border_color, {hub_info["iso2"]: d.accent})
    hp = (hub_info["lon"], hub_info["lat"])
    vmax = max(p[1] for p in pairs)
    col = line_color or d.accent
    for l, v, info in sorted(pairs, key=lambda p: p[1]):
        pp = (info["lon"], info["lat"])
        a, b = (pp, hp) if direction == "in" else (hp, pp)
        curve = _bezier(a, b, bend=0.22 if pp[0] < hp[0] else -0.22)
        w = (1.0 + 6 * v / vmax) * s
        ax.plot(curve[:, 0], curve[:, 1], color=rgba(col, 0.22), linewidth=w * 2.4,
                solid_capstyle="round", zorder=4)
        ax.plot(curve[:, 0], curve[:, 1], color=col, linewidth=w, solid_capstyle="round", zorder=5,
                alpha=0.92)
        ax.annotate("", xy=curve[-1], xytext=curve[-6], zorder=6,
                    arrowprops=dict(arrowstyle="-|>", color=col, lw=0,
                                    mutation_scale=(9 + 12 * v / vmax) * s))
        ax.scatter([pp[0]], [pp[1]], s=(25 + 110 * v / vmax) * s ** 2, color=col,
                   edgecolor=d.surface, linewidth=1.2, zorder=7)
    from ._draw import LabelPlacer
    lp = LabelPlacer(fr.fig)
    ax.scatter([hp[0]], [hp[1]], s=300 * s ** 2, color=rgba(d.accent, 0.3), zorder=8, linewidth=0)
    ax.scatter([hp[0]], [hp[1]], s=80 * s ** 2, color=d.accent, edgecolor=d.surface, linewidth=2, zorder=9)
    if hub_label:
        hn = hub_info["ar"] if arabic else hub_info["en"]
        t = ax.annotate(shape(hn), hp, xytext=(0, -13 * s), textcoords="offset points", ha="center",
                        va="top", fontsize=fr.fs(13), fontproperties=font("sans", "heavy", hn),
                        color=d.accent, zorder=10, path_effects=_halo(fr, d.surface))
        lp.try_text(t)
    if not ranking:  # label the map directly, skipping overlaps
        for l, v, info in pairs:
            name = info["ar"] if arabic else (info["en"] if len(info["en"]) <= 16 else l)
            t = ax.annotate(f"{shape(name)} {vf(v)}", (info["lon"], info["lat"]), xytext=(8 * s, 0),
                            textcoords="offset points", ha="left", va="center", fontsize=fr.fs(10.5),
                            fontproperties=font("sans", "bold", name), color=d.text_color, zorder=9,
                            path_effects=_halo(fr, d.surface))
            lp.try_text(t, [((8 * s, 0), "left", "center"), ((-8 * s, 0), "right", "center"),
                            ((0, 9 * s), "center", "bottom"), ((0, -9 * s), "center", "top")])
        return fr.finish()
    # ranked side panel
    bb = ax.get_position()
    n = len(pairs)
    row = min(0.46 * s, (bb.height * fr.H - 0.2 * s) / max(n, 1))
    top_y = bb.y0 + bb.height / 2 + row * n / 2 / fr.H
    px0 = (bb.x0 + bb.width) * fr.W + 0.35 * s if not arabic else 0.35 * s + fr.margin * 0
    px1 = px0 + panel_in - 0.5 * s
    fsz = fr.fs(12.5 if row > 0.4 * s else 11)
    from matplotlib.patches import FancyBboxPatch
    for k, (l, v, info) in enumerate(pairs):
        yc = top_y - (k + 0.5) * row / fr.H
        name = l  # keep the user's own spelling in the list
        img = get_flag(info["iso2"], "round") if show_flags else None
        fl_in = min(0.3 * s, row * 0.7)
        if not arabic:
            x = px0
            fr.fig.text(x / fr.W, yc, f"{k + 1}", ha="left", va="center", fontsize=fsz * 0.9,
                        fontproperties=font("sans", "bold"), color=d.muted_color)
            x += 0.3 * s
            if img is not None:
                place_image(ax, img, (x + fl_in / 2) / fr.W, yc, fl_in)
            x += fl_in + 0.12 * s
            fr.fig.text(x / fr.W, yc + row * 0.12 / fr.H, shape(name), ha="left", va="center",
                        fontsize=fsz, fontproperties=font("sans", "regular", name), color=d.text_color)
            fr.fig.text(px1 / fr.W, yc + row * 0.12 / fr.H, vf(v), ha="right", va="center", fontsize=fsz,
                        fontproperties=font("sans", "bold"), color=d.value_color)
            bx0, bw = x, (px1 - x) * v / vmax
        else:
            x = px1
            fr.fig.text(x / fr.W, yc, f"{k + 1}", ha="right", va="center", fontsize=fsz * 0.9,
                        fontproperties=font("sans", "bold"), color=d.muted_color)
            x -= 0.3 * s
            if img is not None:
                place_image(ax, img, (x - fl_in / 2) / fr.W, yc, fl_in)
            x -= fl_in + 0.12 * s
            fr.fig.text(x / fr.W, yc + row * 0.12 / fr.H, shape(name), ha="right", va="center",
                        fontsize=fsz, fontproperties=font("sans", "bold", name), color=d.text_color)
            fr.fig.text(px0 / fr.W, yc + row * 0.12 / fr.H, vf(v), ha="left", va="center", fontsize=fsz,
                        fontproperties=font("sans", "bold"), color=d.value_color)
            bw = (x - px0) * v / vmax
            bx0 = x - bw
        fr.fig.add_artist(FancyBboxPatch((bx0 / fr.W, yc - row * 0.3 / fr.H), bw / fr.W, 0.045 * s / fr.H,
                                         boxstyle="square,pad=0", transform=fr.fig.transFigure,
                                         facecolor=col, edgecolor="none", alpha=0.85))
    return fr.finish()
