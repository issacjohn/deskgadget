"""Build the vertical 9:16 DeskGadget reel: intro image, captions, Andrew, music.

    python tools/make_reel_vertical.py
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "docs" / "deskgadget-reel-raw.mp4"
OUT = ROOT / "docs" / "deskgadget-reel.mp4"
IMAGE = Path(r"C:\Users\issac_test\Downloads\Gemini_Generated_Image_lw11t2lw11t2lw11.png")
VOICE_DIR = Path(r"C:\Users\issac_test\AppData\Local\Temp\reel_voice")
MUSIC = Path(r"C:\Users\issac_test\AppData\Local\Temp\dgbg_30.m4a")

INTRO = 4.0
GAP = 0.70
VOICE_LEAD = 0.25

TITLES = [
    "The command center",
    "System",
    "Media",
    "Shortcuts",
    "News",
    "Touchpad",
    "Windows",
    "Make it yours",
]
SUBS = [
    "Live stats. Instant controls.",
    "Every stat. Live.",
    "Total audio control.",
    "One tap. It's running.",
    "Your feed. Your rules.",
    "No mouse? No problem.",
    "No Alt-Tab marathon.",
    "Add. Remove. Rearrange.",
]


def ass_time(seconds: float) -> str:
    cs = max(0, int(round(seconds * 100)))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def dialogue(start: float, end: float, style: str, y: int, text: str) -> str:
    return (
        f"Dialogue: 0,{ass_time(start)},{ass_time(end)},{style},,0,0,0,,"
        f"{{\\an5\\pos(540,{y})\\fad(220,220)}}{text}"
    )


def write_ass(path: Path, starts: list[float], total: float) -> None:
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Title,Segoe UI,62,&H00FAF2ED,&H000000FF,&H00000000,&H00000000,-1,0,0,0,"
        "100,100,0,0,1,2,0,5,0,0,0,1",
        "Style: Sub,Segoe UI,34,&H00BAA69A,&H000000FF,&H00000000,&H00000000,0,0,0,0,"
        "100,100,0,0,1,1,0,5,0,0,0,1",
        "Style: Brand,Segoe UI,24,&H00FFE77C,&H000000FF,&H00000000,&H00000000,-1,0,0,0,"
        "100,100,0,0,1,1,0,5,0,0,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        dialogue(0.15, INTRO - 0.05, "Title", 1290, "DeskGadget"),
        dialogue(0.15, INTRO - 0.05, "Sub", 1372, "Your old phone or tablet. Upgraded."),
    ]
    for i, (title, sub) in enumerate(zip(TITLES, SUBS)):
        end = starts[i + 1] - 0.15 if i + 1 < len(starts) else total - 0.4
        start = starts[i] + 0.10
        lines.append(dialogue(start, end, "Title", 1290, title))
        lines.append(dialogue(start, end, "Sub", 1372, sub))
    lines.append(
        f"Dialogue: 0,0:00:00.00,{ass_time(total - 0.6)},Brand,,0,0,0,,"
        "{\\an5\\pos(540,1472)}DeskGadget"
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build() -> None:
    durs = json.load(open(VOICE_DIR / "durs.json"))
    starts = [0.0]
    for i in range(1, len(durs)):
        starts.append(starts[-1] + durs[i - 1] + GAP)
    reel_total = starts[-1] + durs[-1] + 1.0
    total = INTRO + reel_total

    tmp = Path(tempfile.mkdtemp())
    ass = tmp / "reel_captions.ass"
    shifted = [INTRO + s for s in starts]
    write_ass(ass, shifted, total)

    inputs = ["-loop", "1", "-framerate", "30", "-t", f"{INTRO}", "-i", str(IMAGE)]
    inputs += ["-i", str(RAW)]
    for i in range(len(durs)):
        inputs += ["-i", str(VOICE_DIR / f"v{i}.mp3")]
    inputs += ["-stream_loop", "-1", "-i", str(MUSIC)]

    music_idx = 2 + len(durs)
    intro_chain = (
        "[0:v]scale=1080:-2,"
        "pad=1080:1920:0:560:color=0x05070C,"
        "zoompan=z='min(1+0.0075*on,1.9)':"
        "x='max(0,396-(iw/zoom/2))':y='max(0,1015-(ih/zoom/2))':"
        f"d=1:s=1080x1920:fps=30,trim=duration={INTRO},setpts=PTS-STARTPTS,"
        "setsar=1,format=yuv420p[intro]"
    )
    reel_chain = (
        "[1:v]scale=1000:-2,"
        "pad=1080:1920:(ow-iw)/2:330:color=0x05070C,"
        "drawbox=x=40:y=330:w=1000:h=450:color=0x7CE7FF@0.10:t=10,"
        "drawbox=x=40:y=330:w=1000:h=450:color=0x7CE7FF@0.35:t=1,"
        f"trim=duration={reel_total:.2f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[reel]"
    )
    vcat = "[intro][reel]concat=n=2:v=1:a=0[vcat]"
    video_tail = (
        "[vcat]ass=reel_captions.ass,"
        "fade=t=in:st=0:d=0.5,"
        f"fade=t=out:st={total - 0.9:.2f}:d=0.8[vout]"
    )

    afilters = []
    voice_labels = []
    for i in range(len(durs)):
        if i == 0:
            at = 0.8
        else:
            at = INTRO + starts[i] + VOICE_LEAD
        ms = int(at * 1000)
        afilters.append(
            f"[{i + 2}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
            f"adelay={ms}|{ms}[v{i}]"
        )
        voice_labels.append(f"[v{i}]")
    afilters.append("".join(voice_labels) + f"amix=inputs={len(durs)}:normalize=0[voice]")
    afilters.append("[voice]asplit=2[voice_sc][voice_mix]")
    afilters.append(
        f"[{music_idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
        f"atrim=0:{total:.2f},volume=0.30,"
        f"afade=t=in:st=0:d=1.2,afade=t=out:st={max(0.0, total - 2.5):.2f}:d=2.5[music]"
    )
    afilters.append(
        "[music][voice_sc]sidechaincompress=threshold=0.028:ratio=8:attack=8:release=380[duck]"
    )
    afilters.append(
        "[duck][voice_mix]amix=inputs=2:duration=first:normalize=0,"
        "loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
    )

    graph = ";".join([intro_chain, reel_chain, vcat, video_tail] + afilters)
    cmd = [
        FFMPEG,
        "-y",
        *inputs,
        "-filter_complex",
        graph,
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-shortest",
        str(OUT),
    ]
    print("building", OUT)
    proc = subprocess.run(cmd, cwd=str(tmp), capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr[-2500:])
        raise SystemExit(proc.returncode)
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB, {total:.1f}s)")


if __name__ == "__main__":
    build()
