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
                key = name[:31].strip()  # MME truncates names; collapse duplicates
                if not name or key in seen:
                    continue  # PortAudio lists the same device per host API
                lowered = name.lower()
                if "16ch" in lowered or "point" in lowered:
                    continue  # VB-Cable's extra endpoints; one input is enough
                seen.add(key)
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

    def capture_cable(self) -> str:
        """The cable's capture side: the endpoint call apps use as a microphone."""
        if sd is None:
            return ""
        try:
            for device in sd.query_devices():
                name = str(device.get("name", ""))
                lowered = name.lower()
                if (
                    int(device.get("max_input_channels", 0)) > 0
                    and "cable output" in lowered
                    and "point" not in lowered
                ):
                    return name
        except Exception:
            pass
        return ""

    def _cable(self) -> dict | None:
        """The VB-CABLE render side, chosen automatically. No other device."""
        best: dict | None = None
        best_score = 0
        for device in self.devices():
            name = str(device.get("name", "")).lower()
            if "cable input" in name:
                score = 3
            elif "vb-audio" in name or "virtual cable" in name:
                score = 2
            elif "voicemeeter" in name or "virtual cable" in name:
                score = 1
            else:
                continue
            if score > best_score:
                best, best_score = device, score
        return best

    def _device_index(self) -> int:
        cable = self._cable()
        if cable is None:
            raise RuntimeError(
                "Virtual audio cable not found. Install VB-CABLE to use the phone as a microphone."
            )
        self.state["device"] = str(cable["name"])
        return int(cable["index"])

    # -- audio path --------------------------------------------------------
    def _ensure_stream(self) -> None:
        if self._stream is not None:
            return
        index = self._device_index()
        with self._lock:
            if self._stream is not None:
                return
            self._stream = sd.RawOutputStream(
                samplerate=RATE,
                channels=1,
                dtype="int16",
                device=index,
                blocksize=BLOCK,
                latency="low",
            )
            self._stream.start()
            try:
                self.state["actual"] = str(sd.query_devices(index)["name"])
            except Exception:
                self.state["actual"] = ""

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
                missing = "Virtual audio cable not found" in str(exc)
                self._stop.wait(5.0 if missing else 1.5)

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
    def rescan(self) -> list[dict]:
        """Re-enumerate devices, e.g. after the user installs a virtual cable.

        PortAudio has to be restarted to see new endpoints, which is not safe
        while the output thread is in a write. Stop it first, then bring it
        back so the next chunk reopens on the right device.
        """
        was_running = self._thread is not None and self._thread.is_alive()
        self.stop()
        if sd is not None:
            try:
                sd._terminate()
                sd._initialize()
            except Exception:
                pass
        if was_running:
            self.start()
        return self.devices()

    def configure(
        self,
        *,
        enabled: bool | None = None,
        volume: float | None = None,
        muted: bool | None = None,
        gate: bool | None = None,
    ) -> dict:
        if enabled is not None:
            self.state["enabled"] = bool(enabled)
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
