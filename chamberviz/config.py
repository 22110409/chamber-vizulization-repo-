"""Global settings: paths, the default logo, and defaults you can change once."""
from __future__ import annotations

import shutil
import warnings
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ASSETS = PACKAGE_DIR / "assets"
FONTS_DIR = ASSETS / "fonts"
FLAGS_DIR = ASSETS / "flags"
ICONS_DIR = ASSETS / "icons"
MAPS_DIR = ASSETS / "maps"
LOGOS_DIR = ASSETS / "logos"
BACKGROUNDS_DIR = ASSETS / "backgrounds"

# The organisation logo that is added to EVERY chart unless you pass logo=None.
# Put your Amman Chamber logo here once with cv.set_default_logo("path/to/logo.png").
DEFAULT_LOGO = LOGOS_DIR / "amman_chamber.png"

# Defaults used by every chart. Change them with cv.set_defaults(...).
DEFAULTS: dict = {
    "design": "navy_gold",
    "figure_size": (16, 9),
    "logo": "default",            # "default" = DEFAULT_LOGO, None = no logo, or a path
    "logo_alignment": "top-right",
    "logo_size": 0.10,            # logo height as a fraction of the figure height
    "source": None,               # e.g. "Source: Department of Statistics"
    "dpi": 200,
    "flag_style": "round",        # "round" or "rect"
}

_warned_logo = False


def set_defaults(**kwargs) -> None:
    """Change defaults for all later charts, e.g. set_defaults(design="ivory_dots")."""
    for k, v in kwargs.items():
        if k == "figsize":
            k = "figure_size"
        if k not in DEFAULTS:
            raise TypeError(f"Unknown default '{k}'. Valid: {', '.join(DEFAULTS)}")
        DEFAULTS[k] = v


def set_default_logo(path: str | Path) -> Path:
    """Copy your logo into the package so every chart uses it automatically."""
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(src)
    LOGOS_DIR.mkdir(parents=True, exist_ok=True)
    dst = DEFAULT_LOGO.with_suffix(src.suffix.lower())
    for old in LOGOS_DIR.glob("amman_chamber.*"):
        old.unlink()
    shutil.copy(src, dst)
    return dst


def default_logo_path() -> Path | None:
    global _warned_logo
    for p in LOGOS_DIR.glob("amman_chamber.*"):
        return p
    if not _warned_logo:
        warnings.warn(
            "No default logo yet. Run cv.set_default_logo('your_logo.png') once and "
            "it will appear on every chart (or pass logo=None to hide this message).",
            stacklevel=4,
        )
        _warned_logo = True
    return None
