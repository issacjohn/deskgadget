"""Compose the desk hero image from a real phone screenshot."""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "docs" / "screenshots"
W, H = 1600, 900


def gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)
    for y in range(size[1]):
        t = y / max(1, size[1] - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (size[0], y)], fill=color)
    return img


def glow(canvas: Image.Image, center: tuple[int, int], radius: int, color: tuple[int, int, int], alpha: int) -> None:
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.ellipse(
        [center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius],
        fill=(*color, alpha),
    )
    layer = layer.filter(ImageFilter.GaussianBlur(radius * 0.55))
    canvas.alpha_composite(layer)


def rounded(img: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.size[0], img.size[1]], radius=radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def drop_shadow(canvas: Image.Image, box: tuple[int, int, int, int], blur: int, alpha: int) -> None:
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius=40, fill=(0, 0, 0, alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(layer)


def build() -> None:
    random.seed(7)
    canvas = gradient((W, H), (6, 9, 16), (2, 3, 7)).convert("RGBA")

    glow(canvas, (330, 210), 420, (64, 190, 255), 46)
    glow(canvas, (1290, 250), 380, (255, 96, 170), 40)
    glow(canvas, (900, 720), 460, (150, 110, 255), 32)

    # desk surface: a faint horizontal band with soft reflections
    desk = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(desk).rectangle([0, 690, W, H], fill=(12, 16, 24, 255))
    desk = desk.filter(ImageFilter.GaussianBlur(24))
    canvas.alpha_composite(desk)

    # keyboard hint, blurred
    kb = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    kd = ImageDraw.Draw(kb)
    kd.rounded_rectangle([120, 760, 1480, 1020], radius=26, fill=(20, 25, 35, 255))
    for row in range(4):
        for col in range(14):
            x = 150 + col * 94
            y = 780 + row * 58
            kd.rounded_rectangle([x, y, x + 78, y + 44], radius=8, fill=(30, 36, 48, 255))
    kb = kb.filter(ImageFilter.GaussianBlur(7))
    canvas.alpha_composite(kb)

    shot = Image.open(SHOTS / "home.jpg").convert("RGB")
    screen_w = 1120
    screen_h = int(shot.height * screen_w / shot.width)
    shot = shot.resize((screen_w, screen_h), Image.LANCZOS)
    shot = rounded(shot, 22)

    pad = 12
    frame_w, frame_h = screen_w + pad * 2, screen_h + pad * 2
    frame = Image.new("RGBA", (frame_w, frame_h), (0, 0, 0, 0))
    fd = ImageDraw.Draw(frame)
    fd.rounded_rectangle([0, 0, frame_w, frame_h], radius=34, fill=(10, 14, 22, 255))
    fd.rounded_rectangle([1, 1, frame_w - 2, frame_h - 2], radius=33, outline=(90, 110, 140, 140), width=2)
    frame.alpha_composite(shot, (pad, pad))

    angle = -5.0
    rotated = frame.rotate(angle, expand=True, resample=Image.BICUBIC)

    x = (W - rotated.width) // 2 + 40
    y = (H - rotated.height) // 2 - 90

    drop_shadow(canvas, (x + 20, y + 34, x + rotated.width - 10, y + rotated.height + 10), 46, 210)
    canvas.alpha_composite(rotated, (x, y))

    # a soft highlight across the glass
    sheen = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(sheen).polygon(
        [(x + 60, y + 40), (x + 360, y + 20), (x + 200, y + rotated.height - 30), (x - 60, y + rotated.height - 60)],
        fill=(255, 255, 255, 14),
    )
    canvas.alpha_composite(sheen.filter(ImageFilter.GaussianBlur(28)))

    # vignette
    vig = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    vd = ImageDraw.Draw(vig)
    for i in range(90):
        alpha = int(2.0 * i)
        vd.rectangle([i, i, W - i, H - i], outline=(0, 0, 0, alpha))
    canvas.alpha_composite(vig.filter(ImageFilter.GaussianBlur(60)))

    out = SHOTS / "desk.jpg"
    canvas.convert("RGB").save(out, "JPEG", quality=90, optimize=True)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    build()
