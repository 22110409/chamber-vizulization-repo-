"""Preview sheets: all designs side by side, icon browser, flag browser."""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from .assets_lookup import all_countries, flag, icon_char, search_icons
from .text import font, icon_font, shape
from .themes import DESIGNS


def preview_designs(save="designs_preview.png", **kw):
    """Draw the same small bar chart in every design and save one overview image."""
    from .charts_bar import barplot
    from PIL import Image
    import io
    tiles = []
    for name in DESIGNS:
        c = barplot(["A", "B", "C", "D", "E"], [42, 35, 28, 20, 12], design=name, title=name,
                    subtitle="design preview", figure_size=(8, 4.5), logo=None, **kw)
        tiles.append(Image.open(io.BytesIO(c.to_bytes(dpi=80))))
        c.close()
    cols = 2
    w, h = tiles[0].size
    rows = -(-len(tiles) // cols)
    sheet = Image.new("RGB", (cols * w + (cols + 1) * 20, rows * h + (rows + 1) * 20), "white")
    for i, t in enumerate(tiles):
        sheet.paste(t.convert("RGB"), (20 + (i % cols) * (w + 20), 20 + (i // cols) * (h + 20)))
    sheet.save(save)
    return save


def icon_sheet(query="", variant="outline", save=None, columns=10, color="#1f3d4a", limit=120):
    """Contact sheet of icons matching a word, e.g. icon_sheet('truck'). Returns the names."""
    names = search_icons(query, variant, limit=limit)
    if not names:
        print(f"No icons contain '{query}'.")
        return []
    columns = min(columns, len(names))
    rows = -(-len(names) // columns)
    fig = plt.figure(figsize=(columns * 1.5, rows * 1.35 + 0.4), dpi=100)
    fig.patch.set_facecolor("white")
    for i, n in enumerate(names):
        x = (i % columns + 0.5) / columns
        y = 1 - (i // columns + 0.45) / rows * (1 - 0.4 / (rows * 1.35 + 0.4))
        fig.text(x, y, icon_char(n, variant), fontproperties=icon_font(variant), fontsize=26,
                 color=color, ha="center", va="center")
        fig.text(x, y - 0.42 / (rows * 1.35 + 0.4) * 1.0, n, fontsize=7.5, ha="center",
                 va="top", color="#555555")
    save = save or f"icons_{query or 'all'}.png"
    fig.savefig(save, dpi=100)
    plt.close(fig)
    return names


def flag_sheet(save="flags.png", style="round", language="en", columns=12):
    """Every available flag with its country name and ISO code."""
    cs = sorted(all_countries(), key=lambda c: c[language] or c["en"])
    cs = [c for c in cs if flag(c["iso2"], style) is not None]
    rows = -(-len(cs) // columns)
    W, H = columns * 1.35, rows * 1.15
    fig = plt.figure(figsize=(W, H), dpi=100)
    fig.patch.set_facecolor("white")
    for i, c in enumerate(cs):
        cx = (i % columns + 0.5) * 1.35
        cy = H - (i // columns + 0.4) * 1.15
        img = flag(c["iso2"], style)
        h, w = img.shape[:2]
        fw = 0.5
        fh = fw * h / w
        ax = fig.add_axes([(cx - fw / 2) / W, (cy - fh / 2) / H, fw / W, fh / H])
        ax.imshow(img)
        ax.axis("off")
        nm = c[language] or c["en"]
        fig.text(cx / W, (cy - 0.36) / H, shape(nm[:20]), ha="center", va="top", fontsize=6.5,
                 fontproperties=font("sans", "regular", nm), color="#333333")
        fig.text(cx / W, (cy - 0.52) / H, c["iso2"], ha="center", va="top", fontsize=6, color="#888888")
    fig.savefig(save, dpi=110)
    plt.close(fig)
    return save
