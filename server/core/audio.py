"""Phone microphone audio, played on a PC output device.

The phone sends 48 kHz mono PCM16 on `/ws/mic`; this module keeps a small
buffer and writes it to the chosen output. Selecting a virtual cable device
here is what turns the phone into a microphone for call apps.
"""
from __future__ import annotations

import queue
import threading
import time

import numpy as np

try:
    import sounddevice as sd
except Exception:  # missing runtime, e.g. a stripped build
    sd = None

RATE = 48000
BLOCK = 960  # 20 ms


class AudioSink:
    def __init__(self) -> None:
        self._q: queue.Queue[bytes] = queue.Queue(maxsize=150)
        self._stream = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._level = 0.0
        self._last_frame = 0.0
        self._frames = 0
        self._gate_gain = 0.0
        self.state = {
            "enabled": True,
            "device": "",
            "volume": 0.9,
            "muted": False,
            "gate": True,
            "error": "",
        }

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        if sd is None:
            self.state["error"] = "sounddevice is not installed"
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="audio-out", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(2.0)
        self._close_stream()

    def _close_stream(self) -> None:
        with self._lock:
            stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    # -- devices -----------------------------------------------------------
    def devices(self) -> list[dict]:
        if sd is None:
            return []
        out: list[dict] = []
        seen: set[str] = set()
        try:
            for index, device in enumerate(sd.query_devices()):
                if int(device.get("max_output_channels", 0)) <= 0:
                    continue
                name = str(device.get("name", "")).strip()
                if not name or name in seen:
                    continue  # PortAudio lists the same device per host API
                seen.add(name)
                out.append(
                    {
                        "index": index,
                        "name": name,
                        "channels": int(device.get("max_output_channels", 2)),
                        "rate": int(device.get("default_samplerate", 48000)),
                    }
                )
        except Exception as exc:
            self.state["error"] = str(exc)
        return out

    def _device_index(self) -> int | None:
        name = str(self.state.get("device") or "").strip()
        if not name:
            return None  # system default
        for device in self.devices():
            if device["name"] == name:
                return int(device["index"])
        return None

    # -- audio path --------------------------------------------------------
    def _ensure_stream(self) -> None:
        if self._stream is not None:
            return
        with self._lock:
            if self._stream is not None:
                return
            self._stream = sd.RawOutputStream(
                samplerate=RATE,
                channels=1,
                dtype="int16",
                device=self._device_index(),
                blocksize=BLOCK,
                latency="low",
            )
            self._stream.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                try:
                    data = self._q.get(timeout=0.25)
                except queue.Empty:
                    continue
                self._ensure_stream()

                volume = float(self.state.get("volume", 0.9))
                muted = bool(self.state.get("muted"))
                if muted or volume <= 0.001:
                    out = b"\x00" * len(data)
                else:
                    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                    if self.state.get("gate", True):
                        # Hysteresis keeps the room out without clipping words.
                        rms = float(np.sqrt(np.mean((samples / 32768.0) ** 2))) if samples.size else 0.0
                        if rms > 0.012:
                            target = 1.0
                        elif rms < 0.005:
                            target = 0.0
                        else:
                            target = self._gate_gain
                        coef = 0.55 if target > self._gate_gain else 0.06
                        self._gate_gain += (target - self._gate_gain) * coef
                        gain = 0.03 + 0.97 * self._gate_gain
                    else:
                        gain = 1.0
                    samples = samples * volume * gain
                    out = np.clip(samples, -32768, 32767).astype(np.int16).tobytes()
                self._stream.write(out)
                self.state["error"] = ""
            except Exception as exc:
                self.state["error"] = str(exc)
                self._close_stream()
                self._stop.wait(1.5)

    def push(self, data: bytes) -> None:
        """Called for every PCM chunk from the phone."""
        if not data:
            return
        try:
            samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0
            self._level = max(rms, self._level * 0.75)
        except Exception:
            rms = 0.0
        self._frames += 1
        self._last_frame = time.time()
        if not self.state.get("enabled", True):
            return
        try:
            self._q.put_nowait(data)
        except queue.Full:
            try:
                self._q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._q.put_nowait(data)
            except queue.Full:
                pass

    # -- api ---------------------------------------------------------------
    def configure(
        self,
        *,
        enabled: bool | None = None,
        device: str | None = None,
        volume: float | None = None,
        muted: bool | None = None,
        gate: bool | None = None,
    ) -> dict:
        if enabled is not None:
            self.state["enabled"] = bool(enabled)
        if device is not None:
            self.state["device"] = str(device)
            self._close_stream()  # reopen on the next chunk
        if volume is not None:
            self.state["volume"] = max(0.0, min(1.0, float(volume)))
        if muted is not None:
            self.state["muted"] = bool(muted)
        if gate is not None:
            self.state["gate"] = bool(gate)
        return self.snapshot()

    def snapshot(self) -> dict:
        live = time.time() - self._last_frame < 1.5 if self._last_frame else False
        return {
            **self.state,
            "playing": self._stream is not None,
            "live": live,
            "level": round(min(1.0, self._level), 3),
            "frames": self._frames,
            "rate": RATE,
        }
