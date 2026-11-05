"""Capture the phone screen to a tidy JPEG for docs screenshots.

    python tools/capture.py docs/screenshots/media.jpg
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image


def shot(out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "shot.png"
        with raw.open("wb") as handle:
            subprocess.run(
                ["adb", "exec-out", "screencap", "-p"],
                stdout=handle,
                check=True,
            )
        image = Image.open(raw).convert("RGB")
        # the panel is 2400x1080; keep it, just trim the quality a little
        image.save(out, "JPEG", quality=88, optimize=True)
    print(f"{out}  {out.stat().st_size // 1024} KB  {image.width}x{image.height}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: capture.py <out.jpg>")
        raise SystemExit(2)
    shot(Path(sys.argv[1]))
