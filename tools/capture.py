"""Capture a phone screen to a tidy JPEG for docs screenshots.

    python tools/capture.py docs/screenshots/media.jpg
    python tools/capture.py shot.jpg 192.168.0.196:38997   # pick a device
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image


def shot(out: Path, serial: str = "") -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "shot.png"
        with raw.open("wb") as handle:
            subprocess.run(
                ["adb", *(["-s", serial] if serial else []), "exec-out", "screencap", "-p"],
                stdout=handle,
                check=True,
            )
        image = Image.open(raw).convert("RGB")
        image.save(out, "JPEG", quality=88, optimize=True)
    print(f"{out}  {out.stat().st_size // 1024} KB  {image.width}x{image.height}")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print("usage: capture.py <out.jpg> [device serial]")
        raise SystemExit(2)
    shot(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) == 3 else "")
