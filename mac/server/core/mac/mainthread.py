"""Run AppKit/Accessibility work on the main thread.

The server runs uvicorn on a worker thread while AppKit owns the main run loop
(the app window). AppKit asserts hard — SIGTRAP, "Must only be used from the
main thread" — when UI state is changed from the server thread, which is what
happened when focusing a window.

``run()`` dispatches the callable through PyObjC's AppHelper when a run loop is
present, and calls it inline otherwise (source mode runs the server on the main
thread, which is already correct).
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Optional

log = logging.getLogger("deskgadget.mac.mainthread")


def _apphelper():
    try:
        from PyObjCTools import AppHelper

        return AppHelper
    except Exception:
        return None


def run(fn: Callable[[], Any], timeout: float = 3.0, default: Any = None) -> Any:
    """Call ``fn`` on the main thread in a bundled app; inline in source mode."""
    if threading.current_thread() is threading.main_thread():
        return fn()

    helper = _apphelper()
    if helper is None:
        # No AppKit bridge: nothing to marshal. AX calls are thread-safe when
        # the target is another process.
        return fn()

    done = threading.Event()
    box: dict = {}

    def wrapper() -> None:
        try:
            box["value"] = fn()
        except Exception as exc:  # propagate to the caller
            box["error"] = exc
        finally:
            done.set()

    try:
        helper.callAfter(wrapper)
    except Exception:
        log.debug("callAfter failed; running inline", exc_info=True)
        return fn()

    if not done.wait(timeout):
        log.warning("main thread did not run the accessibility task in %.1fs", timeout)
        return default
    if "error" in box:
        raise box["error"]
    return box.get("value")
