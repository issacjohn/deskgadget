"""Grab a frame from two virtual cameras at the same time and compare them."""
import subprocess
import sys
import threading

import imageio_ffmpeg
from PIL import Image, ImageChops

FF = imageio_ffmpeg.get_ffmpeg_exe()
OUT = [r"C:\Users\issac_test\AppData\Local\Temp\pair_a.png",
       r"C:\Users\issac_test\AppData\Local\Temp\pair_b.png"]
NAMES = ["DeskGadget Camera - Pixel 9 Pro XL", "DeskGadget Camera - SM-G980F"]
errors = []


def grab(name, out):
    result = subprocess.run(
        [FF, "-hide_banner", "-loglevel", "error", "-f", "dshow",
         "-i", f"video={name}", "-ss", "1", "-frames:v", "1",
         "-update", "1", "-y", out],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        errors.append((name, result.stderr.strip()[-200:]))


threads = [threading.Thread(target=grab, args=(n, o)) for n, o in zip(NAMES, OUT)]
for t in threads:
    t.start()
for t in threads:
    t.join()

print("errors:", errors)
a = Image.open(OUT[0]).convert("RGB")
b = Image.open(OUT[1]).convert("RGB")
diff = ImageChops.difference(a.resize((320, 180)), b.resize((320, 180)))
mean = sum(diff.convert("L").getdata()) / (320 * 180)
print("sizes:", a.size, b.size, "mean diff:", round(mean, 2))
a.resize((640, 360)).save(r"C:\Users\issac_test\AppData\Local\Temp\pair_a_small.jpg")
b.resize((640, 360)).save(r"C:\Users\issac_test\AppData\Local\Temp\pair_b_small.jpg")
