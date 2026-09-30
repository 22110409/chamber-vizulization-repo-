"""Turn the Lab's settings (size, logos, background, colours) into chamberviz keyword arguments."""
from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from matplotlib.colors import to_hex, to_rgb

from chamberviz.themes import get_design

ROOT = Path(__file__).resolve().parents[1]
DEMO_LOGO = ROOT / "chamberviz" / "assets" / "logos" / "demo_logo.png"

SIZES = {"Design default": None, "Wide 12 × 7": (12, 7), "Landscape 10 × 6": (10, 6),
         "Square 8 × 8": (8, 8), "Portrait 7 × 10": (7, 10)}
LOGO_MODES = ["No logo", "One logo", "Two logos"]
POSITIONS = ["top-right", "top-left", "bottom-right", "bottom-left"]
BACKGROUNDS = ["World map (design default)", "Solid world map", "Dotted world map", "Plain, no map", "My photo"]

# picker key -> label; the value each picker starts with comes from the design (design_colors)
COLORS = {"bg_top": "Background, top", "bg_bottom": "Background, bottom", "bar": "Bars",
          "highlight": "Highlighted bar", "title": "Title", "text": "Labels and values",
          "accent": "Accent (lines, axis, icons)", "map": "Background map"}

# every setting the page sends, in this order, after the design
SETTINGS = ["size", "logo_mode", "logo1", "pos1", "logo2", "pos2",
            "bg_mode", "bg_photo", "bg_opacity", "keep_map",
            "custom", "color_base", "series", *COLORS]


class SettingsError(ValueError):
    """A setting the user has to fix (shown on the page)."""


# ---------------------------------------------------------------- colour helpers
def hex_color(value) -> str:
    """'#AABBCC', 'aabbcc', 'rgb(1,2,3)', 'rgba(1,2,3,1)' -> '#aabbcc' ('' if empty)."""
    if not value:
        return ""
    value = str(value).strip()
    if value.lower().startswith("rgb"):
        r, g, b = (float(n) for n in re.findall(r"[\d.]+", value)[:3])
        return to_hex((r / 255, g / 255, b / 255))
    if re.fullmatch(r"[0-9a-fA-F]{6}", value):
        value = "#" + value
    return to_hex(value)


def mix(a: str, b: str, t: float) -> str:
    """Blend colour a toward colour b by t (0 = a, 1 = b)."""
    ra, rb = to_rgb(a), to_rgb(b)
    return to_hex(tuple(x * (1 - t) + y * t for x, y in zip(ra, rb)))


def luminance(c: str) -> float:
    r, g, b = to_rgb(c)
    return 0.299 * r + 0.587 * g + 0.114 * b


def design_colors(name: str) -> tuple[dict, str]:
    """The design's own colours, as the pickers show them, and its series colours as text."""
    d = get_design(name)
    colors = {"bg_top": d.background[0], "bg_bottom": d.background[1], "bar": d.bar[1],
              "highlight": d.highlight[1], "title": d.title_color, "text": d.text_color,
              "accent": d.accent, "map": d.map_color}
    return {k: hex_color(v) for k, v in colors.items()}, ", ".join(hex_color(c) for c in d.series)


def parse_series(text: str) -> list[str]:
    parts = [p for p in re.split(r"[,\s;]+", text or "") if p]
    try:
        return [hex_color(p) for p in parts]
    except ValueError as exc:
        raise SettingsError(f"Series colours: '{exc}'. Use colours like #1f77b4, separated by commas.")


# ---------------------------------------------------------------- the design
def custom_design(base: str, st: dict):
    """(design for chamberviz, label for the results, make_design(...) code or '').

    Only the colours the user changed (compared with the design the pickers were loaded from) are
    applied, so choosing several designs keeps what makes each design different.
    """
    if not st.get("custom"):
        return base, base, ""
    ref, ref_series = design_colors(st.get("color_base") or base)
    changed = {}
    for key in COLORS:
        value = hex_color(st.get(key))
        if value and value != ref[key]:
            changed[key] = value
    series = parse_series(st.get("series"))
    series_changed = bool(series) and series != parse_series(ref_series)
    if not changed and not series_changed:
        return base, base, ""

    d = get_design(base)
    ch: dict = {}
    bg = (changed.get("bg_top", hex_color(d.background[0])), changed.get("bg_bottom", hex_color(d.background[1])))
    if "bg_top" in changed or "bg_bottom" in changed:
        dark = luminance(bg[1]) < 0.5
        ch.update(background=bg, surface=bg[0], border_color=bg[0],
                  card=mix(bg[0], "#ffffff" if dark else "#000000", 0.08),
                  land_color=mix(bg[0], "#ffffff" if dark else "#000000", 0.12))
        # dark <-> light: the design's text would disappear, so switch it unless the user chose it
        if dark != (luminance(hex_color(d.background[1])) < 0.5):
            changed.setdefault("text", "#e8ecf3" if dark else "#2b2b2b")
            changed.setdefault("title", "#f3f3f3" if dark else "#1f3d4a")
            ch.update(grid_color="#ffffff" if dark else "#9a9a9a")
    if "bar" in changed:
        ch["bar"] = (mix(changed["bar"], "#000000", 0.55), changed["bar"])
    if "highlight" in changed:
        v = changed["highlight"]
        ch["highlight"] = (mix(v, "#000000", 0.5), v)
        if d.highlight_cap:
            ch["highlight_cap"] = v
        if hex_color(d.highlight_value_color) == hex_color(d.highlight[1]):
            ch["highlight_value_color"] = v
        if hex_color(d.sequential[1]) == hex_color(d.highlight[1]):
            ch["sequential"] = (d.sequential[0], v)
    if "title" in changed:
        ch["title_color"] = changed["title"]
    if "text" in changed:
        v = changed["text"]
        ch.update(text_color=v, value_color=v, subtitle_color=mix(v, bg[1], 0.15),
                  muted_color=mix(v, bg[1], 0.35))
    if "accent" in changed:
        v = changed["accent"]
        ch.update(accent=v, axis_color=v, icon_color=v)
        if d.bar_cap:
            ch["bar_cap"] = v
    if "map" in changed:
        ch["map_color"] = changed["map"]
    if series_changed:
        ch["series"] = series
    # the highlighted value is often drawn in the highlight colour: keep it readable on the background
    hv = hex_color(ch.get("highlight_value_color", d.highlight_value_color))
    if abs(luminance(hv) - luminance(bg[1])) < 0.35:
        ch["highlight_value_color"] = ch.get("value_color", hex_color(d.value_color))

    design = replace(d, name=f"{base}+custom", **ch)
    args = ", ".join(f"{k}={v!r}" for k, v in ch.items())
    code = f'cv.make_design("my_colours", base="{base}", {args})'
    return design, f"{base} + my colours", code


# ---------------------------------------------------------------- everything together
def style_options(design: str, st: dict):
    """Return (style kwargs, design label, make_design code). Raises SettingsError."""
    style: dict = {}
    if SIZES.get(st.get("size")):
        style["figure_size"] = SIZES[st["size"]]

    mode = st.get("logo_mode") or "One logo"
    if mode == "No logo":
        style["logo"] = None
    elif mode == "One logo":
        style["logo"] = st.get("logo1") or str(DEMO_LOGO)
        style["logo_alignment"] = st.get("pos1") or "top-right"
    else:
        pos1, pos2 = st.get("pos1") or "top-right", st.get("pos2") or "top-left"
        if pos1 == pos2:
            raise SettingsError("The two logos are in the same corner: pick a different position for logo 2.")
        style["logo"] = [st.get("logo1") or str(DEMO_LOGO), st.get("logo2") or str(DEMO_LOGO)]
        style["logo_alignment"] = [pos1, pos2]

    bg_mode = st.get("bg_mode") or BACKGROUNDS[0]
    if bg_mode == "Solid world map":
        style["background_map"] = "solid"
    elif bg_mode == "Dotted world map":
        style["background_map"] = "dots"
    elif bg_mode == "Plain, no map":
        style["background_map"] = False
    elif bg_mode == "My photo":
        if not st.get("bg_photo"):
            raise SettingsError("Upload a background photo (JPG or PNG), or pick another background.")
        style["background_image"] = st["bg_photo"]
        style["background_image_opacity"] = float(st.get("bg_opacity") or 0.35)
        if not st.get("keep_map"):
            style["background_map"] = False

    style["design"], label, code = custom_design(design, st)
    return style, label, code
