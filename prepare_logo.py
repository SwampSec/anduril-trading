#!/usr/bin/env python3
"""Prepare anduril_trading.png + 512px icon for the app and Desktop shortcut."""
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    raise SystemExit("Install Pillow: pip install pillow")

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "anduril_trading.png"
ICON = ROOT / "anduril_trading_icon.png"


def is_flat_bg(r, g, b):
    if r < 30 and g < 30 and b < 30:
        return True
    if max(r, g, b) - min(r, g, b) > 20:
        return False
    return (r + g + b) / 3 >= 170


def strip_baked_background(im):
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a > 0 and is_flat_bg(r, g, b):
                px[x, y] = (0, 0, 0, 0)


def square_canvas(im, pad_ratio=0.04):
    bbox = im.getbbox()
    if not bbox:
        raise SystemExit("Logo has no visible pixels")
    im = im.crop(bbox)
    cw, ch = im.size
    side = max(cw, ch)
    pad = max(8, int(side * pad_ratio))
    canvas = Image.new("RGBA", (side + pad * 2, side + pad * 2), (0, 0, 0, 0))
    canvas.paste(im, ((side + pad * 2 - cw) // 2, (side + pad * 2 - ch) // 2), im)
    return canvas


def make_icon(im, size=512):
    icon = im.copy()
    icon.thumbnail((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    iw, ih = icon.size
    canvas.paste(icon, ((size - iw) // 2, (size - ih) // 2), icon)
    return canvas


def build(src: Path):
    im = Image.open(src).convert("RGBA")
    alpha = im.getchannel("A")
    transparent_ratio = sum(v < 10 for v in alpha.getdata()) / max(1, alpha.size[0] * alpha.size[1])
    if transparent_ratio < 0.05:
        strip_baked_background(im)
    logo = square_canvas(im)
    icon = make_icon(logo)
    logo.save(OUT, optimize=True)
    icon.save(ICON, optimize=True)
    print(f"Wrote {OUT.name} {logo.size} and {ICON.name} {icon.size}")


if __name__ == "__main__":
    for name in ("anduril_trading.png", "anduril_trading.jpg", "anduril_logo.png"):
        src = ROOT / name
        if src.exists():
            build(src)
            break
    else:
        raise SystemExit("Add anduril_trading.png to this folder, then run: python3 prepare_logo.py")
