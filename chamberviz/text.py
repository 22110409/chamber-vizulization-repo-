"""Fonts, Arabic shaping (letters joined + right-to-left) and number formatting."""
from __future__ import annotations

import os
import re
import textwrap
import warnings

import matplotlib
from matplotlib import font_manager
from matplotlib.font_manager import FontProperties

from .config import FONTS_DIR, ICONS_DIR

try:  # python-bidi >= 0.5
    from bidi import get_display  # type: ignore
except Exception:  # pragma: no cover
    from bidi.algorithm import get_display  # type: ignore
import arabic_reshaper

# ---------------------------------------------------------------- fonts
# Icon glyphs live outside the basic Unicode plane; matplotlib prints a harmless
# warning about them, which we silence.
warnings.filterwarnings("ignore", message=r"Glyph \d+ .* missing from font\(s\) tabler-icons")
for _f in sorted(FONTS_DIR.glob("*.ttf")) + sorted(ICONS_DIR.glob("*.ttf")):
    try:
        font_manager.fontManager.addfont(str(_f))
    except Exception:  # pragma: no cover
        pass

# Each family list is tried glyph by glyph (matplotlib >= 3.6 font fallback),
# so Latin text uses the Latin font and Arabic letters use the Arabic font.
SANS = ["Noto Sans", "Noto Sans Arabic", "DejaVu Sans"]
SERIF = ["Noto Serif Display", "Amiri", "Noto Sans Arabic", "DejaVu Serif"]
ARABIC_FIRST = ["Noto Sans Arabic", "Noto Sans", "DejaVu Sans"]

WEIGHTS = {"regular": "normal", "normal": "normal", "medium": "medium",
           "bold": "bold", "heavy": "heavy", "extrabold": "heavy", "black": "heavy"}


def font(style: str = "sans", weight: str = "regular", text: str | None = None) -> FontProperties:
    fam = SERIF if style == "serif" else SANS
    if text is not None and has_arabic(text) and style != "serif":
        fam = ARABIC_FIRST
    return FontProperties(family=fam, weight=WEIGHTS.get(weight, weight))


_ICON_FONT = {
    "outline": FontProperties(fname=str(ICONS_DIR / "tabler-icons.ttf")),
    "filled": FontProperties(fname=str(ICONS_DIR / "tabler-icons-filled.ttf")),
}


def icon_font(variant: str = "outline") -> FontProperties:
    return _ICON_FONT[variant]


# ---------------------------------------------------------------- Arabic
_AR = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
_reshaper = arabic_reshaper.ArabicReshaper(configuration={"delete_harakat": False})


def has_arabic(s) -> bool:
    return isinstance(s, str) and bool(_AR.search(s))


# Some python-bidi versions do not mirror brackets; detect it once and fix it ourselves.
_MIRROR = str.maketrans("()[]{}<>", ")(][}{><")
_probe = _reshaper.reshape("(ا)")
_NEEDS_MIRROR = get_display(_probe) == _probe[::-1]


def _visual(line: str) -> str:
    out = get_display(_reshaper.reshape(line))
    return out.translate(_MIRROR) if _NEEDS_MIRROR else out


def _native_arabic() -> bool:
    """matplotlib 3.11+ joins Arabic letters and applies right-to-left order itself.

    Reshaping the text again on those versions reverses it, so chamberviz only
    reshapes on older versions. Override with the environment variable
    CHAMBERVIZ_ARABIC=native (never reshape) or CHAMBERVIZ_ARABIC=reshape (always reshape).
    """
    forced = os.environ.get("CHAMBERVIZ_ARABIC", "").strip().lower()
    if forced in ("native", "reshape"):
        return forced == "native"
    major, minor = (int(p) for p in re.findall(r"\d+", matplotlib.__version__)[:2])
    return (major, minor) >= (3, 11)


NATIVE_ARABIC = _native_arabic()


def shape(s) -> str:
    """Return text ready for matplotlib (Arabic joined and in visual order)."""
    if s is None:
        return ""
    s = str(s)
    if not has_arabic(s) or NATIVE_ARABIC:
        return s
    return "\n".join(_visual(line) for line in s.split("\n"))


def wrap(s, width: int | None) -> str:
    s = "" if s is None else str(s)
    if not width or len(s) <= width:
        return s
    return "\n".join(textwrap.wrap(s, width=width, break_long_words=False)) or s


def label(s, width: int | None = None) -> str:
    """Wrap to width (on the logical text) and then shape for display."""
    return shape(wrap(s, width))


# ---------------------------------------------------------------- numbers
def fmt(v, decimals: int = 1, prefix: str = "", suffix: str = "", compact: bool = False,
        thousands: bool = True, value_format=None) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return ""
    if value_format is not None:
        return value_format(v) if callable(value_format) else value_format.format(v)
    if compact:
        a = abs(v)
        for div, sfx in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
            if a >= div:
                return f"{prefix}{v / div:,.{decimals}f}{sfx}{suffix}"
    body = f"{v:,.{decimals}f}" if thousands else f"{v:.{decimals}f}"
    return f"{prefix}{body}{suffix}"


def auto_decimals(values) -> int:
    """How many decimals the data actually uses (0-2)."""
    vals = [abs(float(v)) for v in values if v is not None and v == v]
    if not vals:
        return 0
    for dec in (0, 1, 2):
        if all(abs(round(v, dec) - v) < 1e-9 * max(1, v) for v in vals):
            return dec
    m = max(vals)
    return 0 if m >= 1000 else (1 if m >= 10 else 2)
