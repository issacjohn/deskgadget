"""Build the final vertical reel: intro image, 6 modules, dashboard, outro.

    python tools/make_reel_final.py
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "deskgadget-reel.mp4"
IMAGE = Path(r"C:\Users\issac_test\Downloads\Gemini_Generated_Image_lw11t2lw11t2lw11.png")
DASH = ROOT / "docs" / "screenshots" / "dashboard.jpg"
VOICE_DIR = Path(r"C:\Users\issac_test\AppData\Local\Temp\reel_voice")
MUSIC = Path(r"C:\Users\issac_test\AppData\Local\Temp\dgbg_30.m4a")
CLIPS = Path(r"C:\Users\issac_test\AppData\Local\Temp\reel_clips2")

INTRO = 4.0
GAP = 0.70
LEAD = 0.25

# Narration indices actually used, in screen order (7 is the old outro, skipped).
USED = [0, 1, 2, 3, 4, 5, 6, 8, 9]
TITLES = [
    "The command center",
    "System",
    "Media",
    "Shortcuts",
    "News",
    "Touchpad",
    "Windows",
    "The dashboard",
    "Open source. 100% free.",
]
SUBS = [
    "Live stats. Instant controls.",
    "Every stat. Live.",
    "Total audio control.",
    "One tap. It's running.",
    "Your feed. Your rules.",
    "No mouse? No problem.",
    "No Alt-Tab marathon.",
    "Add. Build. Rearrange.",
    "Android + Windows · iOS in the pipeline",
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


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr[-2000:])
        raise SystemExit(proc.returncode)


def build() -> None:
    durs = json.load(open(VOICE_DIR / "durs.json"))
    used = [durs[i] for i in USED]
    starts = [0.0]
    for d in used[1:]:
        starts.append(starts[-1] + used[len(starts) - 1] + GAP)

    tmp = Path(tempfile.mkdtemp())
    segs: list[Path] = []

    # intro image with a slow push-in
    intro = tmp / "intro.mp4"
    run([
        FFMPEG, "-y", "-loop", "1", "-framerate", "30", "-t", f"{INTRO}", "-i", str(IMAGE),
        "-vf",
        "scale=1080:-2,pad=1080:1920:0:560:color=0x05070C,"
        "zoompan=z='min(1+0.0075*on,1.9)':x='max(0,396-(iw/zoom/2))':"
        "y='max(0,1015-(ih/zoom/2))':d=1:s=1080x1920:fps=30,"
        f"trim=duration={INTRO},setpts=PTS-STARTPTS,setsar=1,format=yuv420p",
        "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an", str(intro),
    ])
    segs.append(intro)

    # six phone screens
    for i in range(7):
        target = used[i] + GAP
        src = CLIPS / f"clip_{i}.mp4"
        dst = tmp / f"seg_{i}.mp4"
        run([
            FFMPEG, "-y", "-i", str(src), "-t", f"{target:.2f}",
            "-vf",
            "scale=1000:-2,pad=1080:1920:(ow-iw)/2:330:color=0x05070C,"
            "drawbox=x=40:y=330:w=1000:h=450:color=0x7CE7FF@0.10:t=10,"
            "drawbox=x=40:y=330:w=1000:h=450:color=0x7CE7FF@0.35:t=1,"
            "setsar=1,format=yuv420p",
            "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an", str(dst),
        ])
        segs.append(dst)

    # dashboard still with a slow zoom
    dash_target = used[7] + GAP
    dash = tmp / "dash.mp4"
    run([
        FFMPEG, "-y", "-loop", "1", "-framerate", "30", "-t", f"{dash_target:.2f}", "-i", str(DASH),
        "-vf",
        "scale=820:-2,pad=1080:1920:(ow-iw)/2:270:color=0x05070C,"
        "zoompan=z='min(1+0.004*on,1.10)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        "d=1:s=1080x1920:fps=30,"
        f"trim=duration={dash_target:.2f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p",
        "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an", str(dash),
    ])
    segs.append(dash)

    # outro glance
    outro_target = used[8] + 1.0
    outro = tmp / "outro.mp4"
    run([
        FFMPEG, "-y", "-i", str(CLIPS / "clip_7.mp4"), "-t", f"{outro_target:.2f}",
        "-vf",
        "scale=1000:-2,pad=1080:1920:(ow-iw)/2:330:color=0x05070C,"
        "drawbox=x=40:y=330:w=1000:h=450:color=0x7CE7FF@0.10:t=10,"
        "drawbox=x=40:y=330:w=1000:h=450:color=0x7CE7FF@0.35:t=1,"
        "setsar=1,format=yuv420p",
        "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an", str(outro),
    ])
    segs.append(outro)

    listing = tmp / "concat.txt"
    listing.write_text("".join(f"file '{s.as_posix()}'\n" for s in segs), encoding="utf-8")
    base = tmp / "base.mp4"
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(base)])

    total = INTRO + starts[-1] + used[-1] + 1.0
    ass = tmp / "reel.ass"
    write_ass(ass, [INTRO + s for s in starts], total)

    inputs = ["-i", str(base)]
    voice_order = []
    for k, idx in enumerate(USED):
        inputs += ["-i", str(VOICE_DIR / f"v{idx}.mp3")]
        voice_order.append(idx)
    inputs += ["-stream_loop", "-1", "-i", str(MUSIC)]

    afilters = []
    labels = []
    for k, idx in enumerate(voice_order):
        at = 0.8 if k == 0 else INTRO + starts[k] + LEAD
        ms = int(at * 1000)
        afilters.append(
            f"[{k + 1}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
            f"adelay={ms}|{ms}[v{k}]"
        )
        labels.append(f"[v{k}]")
    afilters.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0[voice]")
    afilters.append("[voice]asplit=2[voice_sc][voice_mix]")
    mi = 1 + len(labels)
    afilters.append(
        f"[{mi}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
        f"atrim=0:{total:.2f},volume=0.30,"
        f"afade=t=in:st=0:d=1.2,afade=t=out:st={max(0.0, total - 2.5):.2f}:d=2.5[music]"
    )
    afilters.append(
        "[music][voice_sc]sidechaincompress=threshold=0.028:ratio=8:attack=8:release=380[duck]"
    )
    afilters.append(
        "[duck][voice_mix]amix=inputs=2:duration=first:normalize=0,"
        f"loudnorm=I=-16:TP=-1.5:LRA=11,apad=whole_dur={total:.2f}[aout]"
    )
    video = (
        "[0:v]ass=reel.ass,fade=t=in:st=0:d=0.5,"
        f"fade=t=out:st={total - 0.9:.2f}:d=0.8[vout]"
    )
    proc = subprocess.run([
        FFMPEG, "-y", *inputs, "-filter_complex", ";".join([video] + afilters),
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{total:.2f}", str(OUT),
    ], cwd=str(tmp), capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr[-2000:])
        raise SystemExit(proc.returncode)
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB, {total:.1f}s)")


if __name__ == "__main__":
    build()
