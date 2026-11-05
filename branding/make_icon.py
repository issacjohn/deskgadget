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


CARD_W = 1180
CARD_H = 780
CARD_R = 150


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle(
        [0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255
    )
    return m


def card_border(size: tuple[int, int], radius: int, alpha: int, width: int) -> Image.Image:
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(
        [0, 0, size[0] - 1, size[1] - 1],
        radius=radius,
        outline=(255, 255, 255, alpha),
        width=width,
    )
    return layer


def build_icon(with_background: bool = True) -> Image.Image:
    if with_background:
        bg = diagonal_gradient(
            (S, S),
            [(0.0, (10, 12, 22)), (0.55, (6, 8, 16)), (1.0, (3, 4, 9))],
        ).convert("RGBA")

        glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.ellipse([CX - 1040, CY - 940, CX + 300, CY + 260], fill=(88, 84, 255, 120))
        gd.ellipse([CX - 120, CY - 700, CX + 1020, CY + 400], fill=(0, 208, 190, 90))
        gd.ellipse([CX - 760, CY + 160, CX + 420, CY + 1060], fill=(255, 61, 139, 74))
        glow = glow.filter(ImageFilter.GaussianBlur(210))
        bg = Image.alpha_composite(bg, glow)
    else:
        bg = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    card = (CARD_W, CARD_H)
    mask = rounded_mask(card, CARD_R)

    # one clear glass panel: no stacked copies, so it stays legible at 48 px
    shadow = Image.new("RGBA", (CARD_W + 80, CARD_H + 80), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [40, 60, CARD_W + 40, CARD_H + 60], radius=CARD_R + 10, fill=(0, 0, 0, 130)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(80))
    bg.alpha_composite(shadow, (CX - CARD_W // 2 - 40, CY - CARD_H // 2 - 40))

    panel = vivid(CARD_W).resize(card, Image.LANCZOS).convert("RGBA")
    panel.putalpha(mask)
    bg.alpha_composite(panel, (CX - CARD_W // 2, CY - CARD_H // 2))

    # glass sheen across the top half
    ys = Image.new("L", card, 0)
    spx = ys.load()
    for y in range(card[1]):
        v = max(0, int(116 * (1 - y / (card[1] * 0.58))))
        for x in range(card[0]):
            spx[x, y] = v
    sheen = Image.new("RGBA", card, (255, 255, 255, 0))
    sheen.putalpha(Image.composite(ys, Image.new("L", card, 0), mask))
    bg.alpha_composite(sheen, (CX - CARD_W // 2, CY - CARD_H // 2))

    # a soft inner rim, brightest along the top
    edge = card_border(card, CARD_R, 170, 7)
    bg.alpha_composite(edge, (CX - CARD_W // 2, CY - CARD_H // 2))

    # three page dots, the one visual tie to the swipeable deck
    dots = Image.new("RGBA", card, (0, 0, 0, 0))
    dd = ImageDraw.Draw(dots)
    cy = CARD_H - 130
    for i, alpha in enumerate((235, 150, 85)):
        cx = CARD_W // 2 + (i - 1) * 86
        r = 24
        dd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, alpha))
    bg.alpha_composite(dots, (CX - CARD_W // 2, CY - CARD_H // 2))

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
