"""Core Audio access without pyobjc: volume, mute and per-device endpoints.

Uses the plain C API in ``CoreAudio.framework`` through ctypes. That framework
has kept these property selectors stable since the PowerPC days, which is why
this works unchanged from macOS 10.15 to current; the newer Swift-only audio
APIs are deliberately not used.

Every call degrades: if the property is missing on this device (AirPods route
differently, some HDMI sinks ignore mute), we return a value or False and the
caller falls back to AppleScript.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import logging
from typing import Optional

log = logging.getLogger("deskgadget.mac.audio")

# ---- fourcc selectors ------------------------------------------------------
def _fourcc(text: str) -> int:
    value = 0
    for ch in text:
        value = (value << 8) | ord(ch)
    return value


_SYSTEM_OBJECT = 1
_SCOPE_GLOBAL = _fourcc("glob")
_SCOPE_OUTPUT = _fourcc("outp")
_SCOPE_INPUT = _fourcc("inpt")
_ELEMENT_MAIN = 0

_SEL_DEVICES = _fourcc("dev#")
_SEL_DEFAULT_OUTPUT = _fourcc("dOut")
_SEL_DEFAULT_INPUT = _fourcc("dIn")
_SEL_NAME = _fourcc("lnam")
_SEL_UID = _fourcc("uid ")
_SEL_MUTE = _fourcc("mute")
_SEL_VOLUME = _fourcc("volm")
_SEL_STREAMS = _fourcc("slay")

_kCFStringEncodingUTF8 = 0x08000100


class _Address(ctypes.Structure):
    _fields_ = [
        ("mSelector", ctypes.c_uint32),
        ("mScope", ctypes.c_uint32),
        ("mElement", ctypes.c_uint32),
    ]


def _load(paths: list[Optional[str]]):
    for path in paths:
        if not path:
            continue
        try:
            return ctypes.CDLL(path)
        except Exception:
            continue
    return None


_ca = _load(
    [
        "/System/Library/Frameworks/CoreAudio.framework/CoreAudio",
        ctypes.util.find_library("CoreAudio"),
    ]
)
_cf = _load(
    [
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation",
        ctypes.util.find_library("CoreFoundation"),
    ]
)

if _ca is not None:
    _ca.AudioObjectGetPropertyData.argtypes = [
        ctypes.c_uint32,
        ctypes.POINTER(_Address),
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_void_p,
    ]
    _ca.AudioObjectGetPropertyData.restype = ctypes.c_int32
    _ca.AudioObjectGetPropertyDataSize.argtypes = [
        ctypes.c_uint32,
        ctypes.POINTER(_Address),
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    _ca.AudioObjectGetPropertyDataSize.restype = ctypes.c_int32
    _ca.AudioObjectSetPropertyData.argtypes = [
        ctypes.c_uint32,
        ctypes.POINTER(_Address),
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    _ca.AudioObjectSetPropertyData.restype = ctypes.c_int32

if _cf is not None:
    _cf.CFStringGetCString.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_long,
        ctypes.c_uint32,
    ]
    _cf.CFStringGetCString.restype = ctypes.c_bool
    _cf.CFRelease.argtypes = [ctypes.c_void_p]
    _cf.CFRelease.restype = None


def available() -> bool:
    return _ca is not None


def _addr(selector: int, scope: int, element: int = _ELEMENT_MAIN) -> _Address:
    return _Address(selector, scope, element)


def _get_u32(obj: int, selector: int, scope: int, element: int = 0) -> Optional[int]:
    addr = _addr(selector, scope, element)
    value = ctypes.c_uint32(0)
    size = ctypes.c_uint32(ctypes.sizeof(value))
    err = _ca.AudioObjectGetPropertyData(obj, ctypes.byref(addr), 0, None, ctypes.byref(size), ctypes.byref(value))
    return None if err else int(value.value)


def _set_u32(obj: int, selector: int, scope: int, value: int, element: int = 0) -> bool:
    addr = _addr(selector, scope, element)
    data = ctypes.c_uint32(int(value))
    return (
        _ca.AudioObjectSetPropertyData(obj, ctypes.byref(addr), 0, None, ctypes.sizeof(data), ctypes.byref(data))
        == 0
    )


def _get_f32(obj: int, selector: int, scope: int, element: int = 0) -> Optional[float]:
    addr = _addr(selector, scope, element)
    value = ctypes.c_float(0.0)
    size = ctypes.c_uint32(ctypes.sizeof(value))
    err = _ca.AudioObjectGetPropertyData(obj, ctypes.byref(addr), 0, None, ctypes.byref(size), ctypes.byref(value))
    return None if err else float(value.value)


def _set_f32(obj: int, selector: int, scope: int, value: float, element: int = 0) -> bool:
    addr = _addr(selector, scope, element)
    data = ctypes.c_float(float(value))
    return (
        _ca.AudioObjectSetPropertyData(obj, ctypes.byref(addr), 0, None, ctypes.sizeof(data), ctypes.byref(data))
        == 0
    )


def _cf_string(obj: int, selector: int, scope: int = _SCOPE_GLOBAL) -> str:
    if _cf is None:
        return ""
    addr = _addr(selector, scope)
    ref = ctypes.c_void_p()
    size = ctypes.c_uint32(ctypes.sizeof(ref))
    err = _ca.AudioObjectGetPropertyData(obj, ctypes.byref(addr), 0, None, ctypes.byref(size), ctypes.byref(ref))
    if err or not ref.value:
        return ""
    try:
        buf = ctypes.create_string_buffer(1024)
        if _cf.CFStringGetCString(ref, buf, len(buf), _kCFStringEncodingUTF8):
            return buf.value.decode("utf-8", "replace")
        return ""
    finally:
        try:
            _cf.CFRelease(ref)
        except Exception:
            pass


def _device_ids() -> list[int]:
    if _ca is None:
        return []
    addr = _addr(_SEL_DEVICES, _SCOPE_GLOBAL)
    size = ctypes.c_uint32(0)
    if _ca.AudioObjectGetPropertyDataSize(_SYSTEM_OBJECT, ctypes.byref(addr), 0, None, ctypes.byref(size)) != 0:
        return []
    count = size.value // ctypes.sizeof(ctypes.c_uint32)
    if count <= 0:
        return []
    array = (ctypes.c_uint32 * count)()
    if _ca.AudioObjectGetPropertyData(
        _SYSTEM_OBJECT, ctypes.byref(addr), 0, None, ctypes.byref(size), array
    ) != 0:
        return []
    return [int(array[i]) for i in range(count)]


def _channels(obj: int, scope: int) -> int:
    """Total channels in one direction, from the stream configuration."""
    if _ca is None:
        return 0
    addr = _addr(_SEL_STREAMS, scope)
    size = ctypes.c_uint32(0)
    if _ca.AudioObjectGetPropertyDataSize(obj, ctypes.byref(addr), 0, None, ctypes.byref(size)) != 0:
        return 0
    if size.value < 4:
        return 0
    buffer = ctypes.create_string_buffer(size.value)
    if _ca.AudioObjectGetPropertyData(obj, ctypes.byref(addr), 0, None, ctypes.byref(size), buffer) != 0:
        return 0
    try:
        count = ctypes.c_uint32.from_buffer(buffer, 0).value
        total = 0
        # AudioBufferList = { UInt32 mNumberBuffers; AudioBuffer mBuffers[]; }
        # AudioBuffer = { UInt32 channels; UInt32 byteSize; void *data; }.
        # mBuffers is pointer-aligned, so it starts at byte 8 on 64-bit.
        for index in range(min(count, 32)):
            offset = 8 + index * 16
            if offset + 4 > size.value:
                break
            total += ctypes.c_uint32.from_buffer(buffer, offset).value
        return total
    except Exception:
        return 0


def default_output() -> Optional[int]:
    if _ca is None:
        return None
    return _get_u32(_SYSTEM_OBJECT, _SEL_DEFAULT_OUTPUT, _SCOPE_GLOBAL)


def default_input() -> Optional[int]:
    if _ca is None:
        return None
    return _get_u32(_SYSTEM_OBJECT, _SEL_DEFAULT_INPUT, _SCOPE_GLOBAL)


def device_name(device: int) -> str:
    return _cf_string(device, _SEL_NAME) or f"Audio device {device}"


def device_uid(device: int) -> str:
    return _cf_string(device, _SEL_UID) or str(device)


def default_output_name() -> str:
    device = default_output()
    return device_name(device) if device else "Default output"


# --------------------------------------------------------------------------- #
# AppleScript fallback (always present, but only covers the default device)
# --------------------------------------------------------------------------- #
def _osa_volume() -> tuple[float, bool]:
    from . import osascript

    text = osascript("get volume settings")
    level, muted = 0.5, False
    for part in text.split(","):
        key, _, value = part.partition(":")
        key = key.strip()
        value = value.strip()
        if key == "output volume":
            try:
                level = float(value) / 100.0
            except ValueError:
                pass
        elif key == "output muted":
            muted = value.lower() in ("true", "yes")
    return max(0.0, min(1.0, level)), muted


def get_volume() -> tuple[float, bool]:
    device = default_output()
    if device is not None:
        level = _get_f32(device, _SEL_VOLUME, _SCOPE_OUTPUT)
        if level is None:
            channels = _channels(device, _SCOPE_OUTPUT)
            values = [
                _get_f32(device, _SEL_VOLUME, _SCOPE_OUTPUT, element)
                for element in range(1, channels + 1)
            ]
            values = [value for value in values if value is not None]
            level = sum(values) / len(values) if values else None
        if level is not None:
            muted = bool(_get_u32(device, _SEL_MUTE, _SCOPE_OUTPUT) or 0)
            return max(0.0, min(1.0, level)), muted
    return _osa_volume()


def set_volume(level: float) -> bool:
    from . import osascript

    level = max(0.0, min(1.0, float(level)))
    device = default_output()
    if device is not None:
        if _set_f32(device, _SEL_VOLUME, _SCOPE_OUTPUT, level):
            if level > 0:
                _set_u32(device, _SEL_MUTE, _SCOPE_OUTPUT, 0)
            return True
        channels = _channels(device, _SCOPE_OUTPUT)
        ok = False
        for element in range(1, channels + 1):
            ok = _set_f32(device, _SEL_VOLUME, _SCOPE_OUTPUT, level, element) or ok
        if ok:
            if level > 0:
                _set_u32(device, _SEL_MUTE, _SCOPE_OUTPUT, 0)
            return True
    osascript(f"set volume output volume {int(round(level * 100))}")
    if level > 0:
        osascript("set volume output muted false")
    return True


def set_muted(muted: bool) -> bool:
    from . import osascript

    device = default_output()
    if device is not None:
        if _set_u32(device, _SEL_MUTE, _SCOPE_OUTPUT, 1 if muted else 0):
            return True
        # some outputs expose mute per channel
        channels = _channels(device, _SCOPE_OUTPUT)
        ok = False
        for element in range(1, channels + 1):
            ok = _set_u32(device, _SEL_MUTE, _SCOPE_OUTPUT, 1 if muted else 0, element) or ok
        if ok:
            return True
    osascript("set volume output muted true" if muted else "set volume output muted false")
    return True


def toggle_mute() -> bool:
    level, muted = get_volume()
    set_muted(not muted)
    if muted and level > 0:
        set_volume(level)  # restoring volume also clears the mute flag
    return not muted


# --------------------------------------------------------------------------- #
# endpoints (one row per physical device, like the Windows module had)
# --------------------------------------------------------------------------- #
def _kind_ok(device: int, scope: int) -> bool:
    return _channels(device, scope) > 0


def _mute_of(device: int, scope: int) -> bool:
    value = _get_u32(device, _SEL_MUTE, scope)
    if value is not None:
        return bool(value)
    channels = _channels(device, scope)
    for element in range(1, channels + 1):
        value = _get_u32(device, _SEL_MUTE, scope, element)
        if value is not None:
            return bool(value)
    level = _get_f32(device, _SEL_VOLUME, scope)
    return bool(level is not None and level <= 0.001)


def _set_endpoint_mute(device: int, scope: int, muted: bool) -> bool:
    if _set_u32(device, _SEL_MUTE, scope, 1 if muted else 0):
        return True
    channels = _channels(device, scope)
    ok = False
    for element in range(1, channels + 1):
        ok = _set_u32(device, _SEL_MUTE, scope, 1 if muted else 0, element) or ok
    if ok:
        return True
    # no mute property: use the volume as the switch
    return _set_f32(device, _SEL_VOLUME, scope, 0.0 if muted else 1.0)


def endpoints() -> tuple[list[dict], list[dict]]:
    """(outputs, inputs) with stable ids so the phone can toggle one device."""
    outputs: list[dict] = []
    inputs: list[dict] = []
    if _ca is None:
        return outputs, inputs
    for device in _device_ids():
        name = device_name(device)
        if not name:
            continue
        uid = device_uid(device)
        if _kind_ok(device, _SCOPE_OUTPUT):
            outputs.append({"id": uid, "name": name, "muted": _mute_of(device, _SCOPE_OUTPUT)})
        if _kind_ok(device, _SCOPE_INPUT):
            inputs.append({"id": uid, "name": name, "muted": _mute_of(device, _SCOPE_INPUT)})
    outputs.sort(key=lambda item: item["name"].lower())
    inputs.sort(key=lambda item: item["name"].lower())
    return outputs, inputs


def set_endpoint_muted(uid: str, muted: bool) -> bool:
    if not uid or _ca is None:
        return False
    target = None
    for device in _device_ids():
        if device_uid(device) == uid:
            target = device
            break
    if target is None:
        try:
            target = int(uid)
        except ValueError:
            return False
    for scope in (_SCOPE_OUTPUT, _SCOPE_INPUT):
        if _kind_ok(target, scope):
            return _set_endpoint_mute(target, scope, muted)
    return False


def toggle_endpoint(uid: str) -> Optional[bool]:
    """Flip one endpoint and return its new muted state (None if unknown)."""
    if not uid or _ca is None:
        return None
    for device in _device_ids():
        if device_uid(device) != uid:
            continue
        for scope in (_SCOPE_OUTPUT, _SCOPE_INPUT):
            if _kind_ok(device, scope):
                muted = _mute_of(device, scope)
                if _set_endpoint_mute(device, scope, not muted):
                    return not muted
                return None
    return None
