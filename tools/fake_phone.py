"""Pretend to be a second phone, to exercise the multi-camera path."""
import asyncio
import io
import time

from PIL import Image, ImageDraw
import websockets

W, H = 1280, 720


def jpeg(text, color):
    image = Image.new("RGB", (W, H), color)
    draw = ImageDraw.Draw(image)
    draw.rectangle([40, 40, W - 40, H - 40], outline=(255, 255, 255), width=6)
    draw.text((100, 120), text, fill=(255, 255, 255))
    draw.text((100, 200), time.strftime("%H:%M:%S"), fill=(220, 255, 220))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=80)
    return buffer.getvalue()


async def main():
    uri = "ws://127.0.0.1:8787/ws/camera"
    headers = {"X-Device": "Pixel 9 Pro XL"}
    try:
        ws = await websockets.connect(uri, additional_headers=headers)
    except TypeError:
        ws = await websockets.connect(uri, extra_headers=headers)
    async with ws:
        end = time.time() + 40
        while time.time() < end:
            await ws.send(b"\x00" + jpeg("SECOND PHONE", (20, 90, 160)))
            await asyncio.sleep(0.1)


asyncio.run(main())
