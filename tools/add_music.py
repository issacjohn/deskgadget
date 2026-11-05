"""Mix background music under the narration, ducking it while the voice speaks.

    python tools/add_music.py voiced.mp4 music.m4a out.mp4
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
MUSIC_GAIN = 0.30


def build(video: Path, music: Path, out: Path) -> None:
    filt = (
        f"[1:a]atrim=0:60,volume={MUSIC_GAIN},"
        "afade=t=in:st=0:d=1.5,afade=t=out:st=53.5:d=2[m];"
        "[0:a]asplit=2[voice][sc];"
        "[m][sc]sidechaincompress=threshold=0.03:ratio=10:attack=10:release=400[duck];"
        "[duck][voice]amix=inputs=2:duration=first:normalize=0[a]"
    )
    subprocess.run(
        [
            FFMPEG,
            "-y",
            "-i",
            str(video),
            "-stream_loop",
            "-1",
            "-i",
            str(music),
            "-filter_complex",
            filt,
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-shortest",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("usage: add_music.py video music out")
        raise SystemExit(2)
    build(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
