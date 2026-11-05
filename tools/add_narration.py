"""Add a synthesized voiceover to the demo reel.

    python tools/add_narration.py in.mp4 out.mp4

Uses the Windows SAPI voices (no cloud, no account). Each line is generated
separately and delayed to the moment its caption appears, so the voice tracks
the visuals instead of drifting.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
VOICE = "Microsoft Zira Desktop"

# (start seconds, line)
LINES = [
    (0.3, "This is DESKGadget. Your PC, one swipe away."),
    (2.6, "Now playing, with artwork, right on the phone."),
    (6.2, "Tap a headline and it opens on your PC, in front."),
    (10.2, "Switch windows from the phone."),
    (14.2, "Clipboard works both ways."),
    (18.2, "Windows and Android. Free and open source."),
]

PS = """
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice('{voice}')
$s.Rate = 0
$s.Volume = 100
$s.SetOutputToWaveFile('{out}')
$s.Speak('{text}')
$s.SetOutputToNull()
$s.Dispose()
"""


def speak(text: str, out: Path) -> None:
    script = PS.format(voice=VOICE, out=str(out).replace("'", "''"), text=text.replace("'", "''"))
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
        capture_output=True,
    )


def build(src: Path, dst: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        inputs = ["-i", str(src)]
        filters = []
        labels = []
        for i, (start, line) in enumerate(LINES):
            wav = tmpdir / f"line{i}.wav"
            speak(line, wav)
            inputs += ["-i", str(wav)]
            ms = int(start * 1000)
            filters.append(
                f"[{i + 1}:a]aformat=sample_rates=44100:channel_layouts=stereo,"
                f"adelay={ms}|{ms}[a{i}]"
            )
            labels.append(f"[a{i}]")

        mix = "".join(labels) + f"amix=inputs={len(LINES)}:normalize=0,volume=1.4,apad[a]"
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
