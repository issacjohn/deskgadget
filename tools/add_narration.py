"""Add a neural voiceover to the demo reel.

    python tools/add_narration.py in.mp4 out.mp4

Uses edge-tts (Microsoft's neural voices over the network) and places each line
at the moment its caption appears, so the voice tracks the visuals.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

import edge_tts
import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
VOICE = "en-US-AvaNeural"

# (start seconds, spoken line)
LINES = [
    (0.0, "Your old phone or tablet just became the control panel for your PC."),
    (4.6, "Now playing, with artwork, volume, and every microphone."),
    (9.4, "Tap a headline, and it opens on your desktop, already in front."),
    (14.4, "Switch between windows without touching the mouse."),
    (18.4, "Clipboard goes both ways. Read it here, send text back."),
    (23.6, "Wake another machine, check the battery, and add modules without rebuilding the app."),
    (29.6, "DESKGadget. Windows and Android."),
]


def build(src: Path, dst: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)

        async def synth() -> None:
            for i, (_, line) in enumerate(LINES):
                await edge_tts.Communicate(line, VOICE).save(str(tmpdir / f"line{i}.mp3"))

        asyncio.run(synth())

        inputs = ["-i", str(src)]
        filters = []
        labels = []
        for i, (start, _) in enumerate(LINES):
            inputs += ["-i", str(tmpdir / f"line{i}.mp3")]
            ms = int(start * 1000)
            filters.append(
                f"[{i + 1}:a]aformat=sample_rates=44100:channel_layouts=stereo,"
                f"adelay={ms}|{ms}[a{i}]"
            )
            labels.append(f"[a{i}]")

        mix = "".join(labels) + f"amix=inputs={len(LINES)}:normalize=0,apad[a]"
        cmd = [
            FFMPEG,
            "-y",
            *inputs,
            "-filter_complex",
            ";".join(filters + [mix]),
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-shortest",
            str(dst),
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    print(f"wrote {dst} ({dst.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: add_narration.py in.mp4 out.mp4")
        raise SystemExit(2)
    build(Path(sys.argv[1]), Path(sys.argv[2]))
