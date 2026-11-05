"""Build a vertical demo reel from a landscape screen recording.

    python tools/make_reel.py raw.mp4 out.mp4

The phone UI is a 16:9 landscape app, so the reel puts it on a 1080x1920 canvas
with a dark backdrop and timed captions underneath — the same shape as a phone
demo reel, without pretending the app is portrait.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
# ffmpeg filter syntax treats ':' as an option separator, so escape the drive
FONT = r"C\:/Windows/Fonts/segoeui.ttf"
FONT_BOLD = r"C\:/Windows/Fonts/segoeuib.ttf"

# (start, end, caption, sub-caption)
CAPTIONS = [
    (0.0, 7.2, "DESKGADGET", "That old device just got an upgrade"),
    (7.2, 13.6, "System", "Your PC stats. Live."),
    (13.6, 19.3, "Media", "Music, volume, mics. All in control."),
    (19.3, 24.6, "Shortcuts", "One tap. Apps and games."),
    (24.6, 30.5, "News", "Your feed. Your interests."),
    (30.5, 35.0, "Weather", "Right now. What comes next."),
    (35.0, 43.0, "Not just a dashboard", "Switch, share, wake, monitor."),
    (43.0, 49.2, "Make it yours", "Custom modules. Endless possibilities."),
    (49.2, 55.5, "DESKGADGET", "Windows + Android. 100% free."),
]


def drawtext(text: str, y: int, size: int, font: str, accent: str, start: float, end: float) -> str:
    safe = text.replace(":", r"\:").replace("'", r"\'")
    return (
        f"drawtext=fontfile='{font}':text='{safe}':fontcolor={accent}:fontsize={size}"
        f":x=(w-text_w)/2:y={y}:enable='between(t,{start},{end})':expansion=none"
    )


def build(raw: Path, out: Path) -> None:
    filters = [
        # phone screen, centred on a dark canvas
        "scale=1000:-2",
        "pad=1080:1920:(ow-iw)/2:330:color=0x05070C",
    ]
    for start, end, title, sub in CAPTIONS:
        filters.append(drawtext(title, 1250, 58, FONT_BOLD, "#EDF2FA", start, end))
        filters.append(drawtext(sub, 1330, 34, FONT, "#9AA6BA", start, end))

    filters += [
        drawtext("DESKGADGET", 1450, 24, FONT_BOLD, "#7CE7FF", 0.0, 55.5),
        "fade=t=in:st=0:d=0.4",
        "fade=t=out:st=54.4:d=0.8",
    ]

    cmd = [
        FFMPEG,
        "-y",
        "-i",
        str(raw),
        "-vf",
        ",".join(filters),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
        "-t", "55.5",
        "-an",
        str(out),
    ]
    print(" ".join(cmd[:4]), "...")
    subprocess.run(cmd, check=True)
    print(f"wrote {out}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: make_reel.py raw.mp4 out.mp4")
        raise SystemExit(2)
    build(Path(sys.argv[1]), Path(sys.argv[2]))
