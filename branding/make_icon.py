"""Generates the DeskGadget icon and every Android density from one source.

Run:  python branding/make_icon.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "branding"
RES = ROOT / "android" / "app" / "src" / "main" / "res"
BRAND.mkdir(parents=True, exist_ok=True)

S = 2048
CX = CY = S // 2
OUTER_R = 780
INNER_R = 372

CYAN = (77, 226, 255)
IRIS = (124, 107, 255)
VIOLET = (192, 107, 255)
PINK = (255, 90, 158)


def vertical_gradient(size: tuple[int, int], stops: list[tuple[float, tuple[int, int, int]]]) -> Image.Image:
    w, h = size
    img = Image.new("RGB", (1, h))
    px = img.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        for i in range(len(stops) - 1):
            p0, c0 = stops[i]
            p1, c1 = stops[i + 1]
            if p0 <= t <= p1:
                k = (t - p0) / max(p1 - p0, 1e-6)
                px[0, y] = (
                    int(c0[0] + (c1[0] - c0[0]) * k),
                    int(c0[1] + (c1[1] - c0[1]) * k),
                    int(c0[2] + (c1[2] - c0[2]) * k),
                )
                break
    return img.resize((w, h), Image.BICUBIC)


def diagonal_gradient(size: tuple[int, int], stops) -> Image.Image:
    w, h = size
    diag = int(math.hypot(w, h)) + 8
    g = vertical_gradient((diag, diag), stops).rotate(-45, resample=Image.BICUBIC, expand=False)
    left = (diag - w) // 2
    top = (diag - h) // 2
    return g.crop((left, top, left + w, top + h))


def diamond_mask(size: int, radius: float, blur: float) -> Image.Image:
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    cx = cy = size // 2
    d.polygon([(cx, cy - radius), (cx + radius, cy), (cx, cy + radius), (cx - radius, cy)], fill=255)
    if blur:
        m = m.filter(ImageFilter.GaussianBlur(blur))
        m = m.point(lambda v: 255 if v > 126 else 0)
    return m


def diamond_stroke(size: int, radius: float, width: int, blur: float = 0) -> Image.Image:
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    cx = cy = size // 2
    r = radius
    d.line(
        [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy), (cx, cy - r)],
        fill=255,
        width=width,
        joint="curve",
    )
    if blur:
        m = m.filter(ImageFilter.GaussianBlur(blur))
    return m


def half_mask(size: int, upper_left: bool) -> Image.Image:
    """Soft diagonal falloff instead of a hard triangle, so bevels fade out."""
    diag = int(math.hypot(size, size)) + 8
    g = vertical_gradient(
        (diag, diag),
        [(0.0, (255, 255, 255)), (1.0, (0, 0, 0))] if upper_left
        else [(0.0, (0, 0, 0)), (1.0, (255, 255, 255))],
    ).convert("L").rotate(-45, resample=Image.BICUBIC, expand=False)
    left = (diag - size) // 2
    return g.crop((left, left, left + size, left + size))


def vivid(size: int) -> Image.Image:
    return diagonal_gradient(
        (size, size),
        [(0.0, CYAN), (0.34, IRIS), (0.68, VIOLET), (1.0, PINK)],
    ).convert("RGBA")


def build_icon(with_background: bool = True) -> Image.Image:
    if with_background:
        bg = diagonal_gradient(
            (S, S),
            [(0.0, (9, 13, 25)), (0.5, (6, 8, 16)), (1.0, (3, 4, 9))],
        ).convert("RGBA")

        glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.ellipse([CX - 980, CY - 900, CX + 380, CY + 420], fill=(88, 84, 255, 120))
        gd.ellipse([CX + 40, CY - 620, CX + 980, CY + 520], fill=(0, 208, 190, 92))
        gd.ellipse([CX - 640, CY + 220, CX + 520, CY + 1020], fill=(255, 61, 139, 76))
        glow = glow.filter(ImageFilter.GaussianBlur(200))
        bg = Image.alpha_composite(bg, glow)
    else:
        bg = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    gradient = vivid(S)

    # soft glow behind the ring
    ring_glow = diamond_stroke(S, OUTER_R, 30, blur=54)
    layer = gradient.copy()
    layer.putalpha(ring_glow.point(lambda v: int(v * 0.5)))
    bg = Image.alpha_composite(bg, layer)

    # the ring itself
    ring = diamond_stroke(S, OUTER_R, 15, blur=2)
    layer = gradient.copy()
    layer.putalpha(ring)
    bg = Image.alpha_composite(bg, layer)

    # inner diamond: colour bloom, then solid face
    inner = diamond_mask(S, INNER_R, 20)
    bloom_mask = inner.filter(ImageFilter.GaussianBlur(90)).point(lambda v: int(v * 0.75))
    layer = gradient.copy()
    layer.putalpha(bloom_mask)
    bg = Image.alpha_composite(bg, layer)

    core = vertical_gradient(
        (S, S),
        [(0.0, CYAN), (0.42, IRIS), (0.75, VIOLET), (1.0, PINK)],
    ).convert("RGBA")
    core.putalpha(inner)
    bg = Image.alpha_composite(bg, core)

    # bevel: light on the top-left edges, shade on the bottom-right
    hi = Image.composite(
        diamond_stroke(S, INNER_R - 6, 20, blur=9),
        Image.new("L", (S, S), 0),
        half_mask(S, upper_left=True),
    )
    layer = Image.new("RGBA", (S, S), (255, 255, 255, 0))
    layer.putalpha(hi.point(lambda v: int(v * 0.55)))
    bg = Image.alpha_composite(bg, layer)

    lo = Image.composite(
        diamond_stroke(S, INNER_R - 6, 22, blur=11),
        Image.new("L", (S, S), 0),
        half_mask(S, upper_left=False),
    )
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    layer.putalpha(lo.point(lambda v: int(v * 0.30)))
    bg = Image.alpha_composite(bg, layer)

    return bg


def main() -> None:
    icon = build_icon(True).resize((1024, 1024), Image.LANCZOS)
    icon.save(BRAND / "icon.png")
    icon.resize((512, 512), Image.LANCZOS).save(BRAND / "icon-512.png")
    icon.save(
        BRAND / "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    # adaptive icon foreground: mark only, inside the 66% safe zone
    mark = build_icon(False)
    size = int(2048 * 0.62)
    fg = Image.new("RGBA", (2048, 2048), (0, 0, 0, 0))
    fg.alpha_composite(mark.resize((size, size), Image.LANCZOS), ((2048 - size) // 2, (2048 - size) // 2))
    fg = fg.resize((432, 432), Image.LANCZOS)
    fg.save(BRAND / "icon-foreground.png")
    (RES / "drawable-nodpi").mkdir(parents=True, exist_ok=True)
    fg.save(RES / "drawable-nodpi" / "ic_launcher_foreground.png")

    for folder, px in {
        "mipmap-mdpi": 48,
        "mipmap-hdpi": 72,
        "mipmap-xhdpi": 96,
        "mipmap-xxhdpi": 144,
        "mipmap-xxxhdpi": 192,
    }.items():
        d = RES / folder
        d.mkdir(parents=True, exist_ok=True)
        icon.resize((px, px), Image.LANCZOS).save(d / "ic_launcher.png")
        big = icon.resize((px * 4, px * 4), Image.LANCZOS).convert("RGBA")
        circle = Image.new("L", (px * 4, px * 4), 0)
        ImageDraw.Draw(circle).ellipse([0, 0, px * 4 - 1, px * 4 - 1], fill=255)
        big.putalpha(circle)
        big.resize((px, px), Image.LANCZOS).save(d / "ic_launcher_round.png")

    print("icon written")


if __name__ == "__main__":
    main()
