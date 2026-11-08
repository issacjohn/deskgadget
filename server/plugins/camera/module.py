"""Camera bridge: the phone renders this page and sends frames to the PC.

The block is deliberately declarative: the app owns the camera, the preview and
the front/back switch. The server only stores the latest JPEG and exposes it for
testing and for the future virtual-camera stage.
"""
from __future__ import annotations

from core.base import Module as BaseModule


class Module(BaseModule):
    async def update(self) -> None:
        # nothing to poll: frames arrive out of band on /api/camera/frame
        pass

    def page(self) -> dict:
        return {
            "blocks": [
                {
                    "type": "camera",
                    "label": "CAMERA",
                    "title": "Phone camera",
                    "hint": "The preview is exactly what the PC receives.",
                }
            ]
        }
