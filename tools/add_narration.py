"""Add a neural voiceover to the demo reel.

    python tools/add_narration.py in.mp4 out.mp4

Uses edge-tts (Microsoft's neural voices over the network) and places each line
at the moment its caption appears, so the voice tracks the visuals.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import edge_tts
import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
# override with DG_VOICE, e.g. en-US-AndrewNeural (male)
VOICE = os.environ.get("DG_VOICE", "en-US-AvaNeural")

# (start seconds, spoken line)
LINES = [
    (0.25, "Got an old phone or tablet lying around? Turn it into your PC's ultimate control panel with DeskGadget."),
    (7.56, "Keep an eye on everything. CPU, RAM, storage, and network stats, all live."),
    (13.96, "Control your media, check what's playing, adjust volume, and manage all your mics."),
    (19.71, "Launch your favorite apps and Steam games with just one tap. No digging around."),
    (25.01, "Stay in the loop with news picked by you. Found something interesting? Open it straight on your PC."),
    (30.93, "Check the weather right now, see what's coming next, and plan your week."),
    (35.32, "And that's not even everything. Switch windows, share your clipboard, wake up another PC, and check battery levels."),
    (42.71, "Want more? Add your own modules or build one from scratch. No app rebuild needed. Make it yours."),
    (49.47, "DeskGadget. Your devices, your setup. Completely free on Windows and Android."),
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
