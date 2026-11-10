"""Entry point for the standalone DeskGadget.app.

The dashboard is shown in a native ``WKWebView`` window — never in the default
browser. The app is a normal Dock application with an App menu, an Edit menu
(so copy/paste works inside the dashboard) and a menu bar item for quick
access. Closing the window keeps the server running; clicking the Dock icon or
"Open DeskGadget" brings it back.

uvicorn runs on a worker thread (it skips signal handlers off the main thread)
and AppKit owns the main run loop.

Source installs keep using ``python -m server.main``; this file is only the
bundle entry point. ``--server-only`` runs headless, ``--background`` starts
without a window (used by a hidden login item).
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

PORT = int(os.environ.get("DESKGADGET_PORT", "8787"))

_SERVER = None
_PORT = PORT
log = logging.getLogger("deskgadget.entry")

SHOW_NOTIFICATION = "com.deskgadget.show"


def _alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=0.8) as response:
            return response.status == 200
    except Exception:
        return False


def _signal_show() -> None:
    """Ask the already-running instance to bring its window forward."""
    try:
        from Foundation import NSDistributedNotificationCenter

        NSDistributedNotificationCenter.defaultCenter().postNotificationName_object_(
            SHOW_NOTIFICATION, None
        )
    except Exception:
        log.debug("could not signal the running instance", exc_info=True)


def _ask_permissions(kinds=None) -> None:
    """Trigger the real macOS permission dialogs once, off the UI thread."""
    try:
        from server.core import mac

        result = mac.request_missing_permissions(kinds=kinds)
        log.info("permission prompts: %s", result)
    except Exception:
        log.exception("could not request permissions")


def _menu_available() -> bool:
    try:
        import AppKit  # noqa: F401
        import Foundation  # noqa: F401
        import objc  # noqa: F401
        import WebKit  # noqa: F401

        return True
    except Exception:
        log.exception("native window support unavailable")
        return False


def _run_app(server) -> int:
    from AppKit import (
        NSApp,
        NSApplication,
        NSApplicationActivationPolicyRegular,
        NSBackingStoreBuffered,
        NSMakeRect,
        NSMenu,
        NSMenuItem,
        NSStatusBar,
        NSVariableStatusItemLength,
        NSViewHeightSizable,
        NSViewWidthSizable,
        NSWindow,
        NSWindowStyleMaskClosable,
        NSWindowStyleMaskMiniaturizable,
        NSWindowStyleMaskResizable,
        NSWindowStyleMaskTitled,
    )
    from Foundation import (
        NSDistributedNotificationCenter,
        NSObject,
        NSURL,
        NSURLRequest,
    )
    from WebKit import WKWebView, WKWebViewConfiguration
    import objc

    from server.core.paths import data_dir

    dashboard_url = f"http://localhost:{_PORT}"

    class DashboardWindow(NSObject):
        def init(self):
            self = objc.super(DashboardWindow, self).init()
            if self is None:
                return None
            style = (
                NSWindowStyleMaskTitled
                | NSWindowStyleMaskClosable
                | NSWindowStyleMaskMiniaturizable
                | NSWindowStyleMaskResizable
            )
            frame = NSMakeRect(0, 0, 1180, 820)
            window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                frame, style, NSBackingStoreBuffered, False
            )
            window.setTitle_("DeskGadget")
            window.setMinSize_((900, 600))
            window.setReleasedWhenClosed_(False)
            window.setFrameAutosaveName_("DeskGadgetMain")
            window.center()

            config = WKWebViewConfiguration.alloc().init()
            web = WKWebView.alloc().initWithFrame_configuration_(frame, config)
            web.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
            web.setAllowsBackForwardNavigationGestures_(True)
            window.setContentView_(web)

            web.loadRequest_(NSURLRequest.requestWithURL_(NSURL.URLWithString_(dashboard_url)))

            self.window = window
            self.web = web
            return self

        def show(self):
            try:
                self.window.makeKeyAndOrderFront_(None)
                NSApp.activateIgnoringOtherApps_(True)
            except Exception:
                log.debug("could not show the window", exc_info=True)

        def reload(self):
            try:
                self.web.reload_()
            except Exception:
                pass

        # distributed notification from a second `open` of the bundle
        @objc.IBAction
        def showFromOther_(self, note):
            self.show()

    controller = DashboardWindow.alloc().init()

    class AppDelegate(NSObject):
        def applicationShouldHandleReopen_hasVisibleWindows_(self, app, flag):
            controller.show()
            threading.Thread(target=_ask_permissions, daemon=True).start()
            return True

        def applicationDidFinishLaunching_(self, note):
            background = "--background" in sys.argv or os.environ.get("DESKGADGET_BACKGROUND") == "1"
            if background:
                log.info("started in the background")
                return
            # A login item launched with `hidden:true` arrives already hidden;
            # do not steal focus in that case.
            if app.isHidden():
                log.info("started hidden at login")
                return

            from server.core import mac

            first_run = not mac.permissions_already_requested()
            app.activateIgnoringOtherApps_(True)
            if first_run and mac.accessibility_trusted() is not True:
                # TCC presents the Accessibility prompt reliably on the main
                # thread, with the app already active.
                mac.request_accessibility()

            controller.show()
            log.info("dashboard window shown")

            if first_run:
                threading.Thread(
                    target=_ask_permissions,
                    args=(["screen_recording", "automation"],),
                    daemon=True,
                ).start()

        def applicationWillTerminate_(self, note):
            global _SERVER
            if _SERVER is not None:
                _SERVER.should_exit = True

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)

    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)

    NSDistributedNotificationCenter.defaultCenter().addObserver_selector_name_object_(
        controller, "showFromOther:", SHOW_NOTIFICATION, None
    )

    # ---- App menu (About / Hide / Quit) -----------------------------------
    main_menu = NSMenu.alloc().init()
    app_item = NSMenuItem.alloc().init()
    main_menu.addItem_(app_item)
    app_menu = NSMenu.alloc().init()
    app_item.setSubmenu_(app_menu)
    app_menu.addItem_(
        NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "About DeskGadget", "orderFrontStandardAboutPanel:", ""
        )
    )
    app_menu.addItem_(NSMenuItem.separatorItem())
    app_menu.addItem_(
        NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Hide DeskGadget", "hide:", "h")
    )
    app_menu.addItem_(
        NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit DeskGadget", "terminate:", "q")
    )

    # ---- Edit menu: keyboard shortcuts inside the web view -----------------
    edit_item = NSMenuItem.alloc().init()
    main_menu.addItem_(edit_item)
    edit_menu = NSMenu.alloc().initWithTitle_("Edit")
    edit_item.setSubmenu_(edit_menu)
    for title, selector, key in (
        ("Undo", "undo:", "z"),
        ("Redo", "redo:", "Z"),
        ("Cut", "cut:", "x"),
        ("Copy", "copy:", "c"),
        ("Paste", "paste:", "v"),
        ("Select All", "selectAll:", "a"),
    ):
        edit_menu.addItem_(
            NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, selector, key)
        )
    app.setMainMenu_(main_menu)

    # ---- menu bar item -----------------------------------------------------
    class MenuController(NSObject):
        @objc.IBAction
        def openDashboard_(self, sender):
            controller.show()

        @objc.IBAction
        def reloadDashboard_(self, sender):
            controller.reload()
            controller.show()

        @objc.IBAction
        def openData_(self, sender):
            subprocess.Popen(
                ["/usr/bin/open", str(data_dir())],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        @objc.IBAction
        def openLoginItems_(self, sender):
            for url in (
                "x-apple.systempreferences:com.apple.LoginItems-Settings.extension",
                "x-apple.systempreferences:com.apple.preference.users?LoginItems",
            ):
                if subprocess.run(["/usr/bin/open", url], capture_output=True).returncode == 0:
                    return

        @objc.IBAction
        def quitApp_(self, sender):
            global _SERVER
            if _SERVER is not None:
                _SERVER.should_exit = True
            NSApplication.sharedApplication().terminate_(None)

    menu_controller = MenuController.alloc().init()
    status = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
    status.button().setTitle_("DG")
    status.button().setToolTip_("DeskGadget")

    menu = NSMenu.alloc().init()
    menu.setAutoenablesItems_(False)
    header = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        f"DeskGadget · localhost:{_PORT}", None, ""
    )
    header.setEnabled_(False)
    menu.addItem_(header)
    menu.addItem_(NSMenuItem.separatorItem())

    def add(title: str, action: str, key: str = "") -> None:
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
        item.setTarget_(menu_controller)
        item.setEnabled_(True)
        menu.addItem_(item)

    add("Open DeskGadget", "openDashboard:", "d")
    add("Reload Dashboard", "reloadDashboard:", "r")
    menu.addItem_(NSMenuItem.separatorItem())
    add("Open Data Folder", "openData:")
    add("Login Items…", "openLoginItems:")
    menu.addItem_(NSMenuItem.separatorItem())
    add("Quit DeskGadget", "quitApp:", "q")
    status.setMenu_(menu)

    log.info("app ready (window + DG menu bar) on localhost:%s", _PORT)
    app.run()
    return 0


def main() -> int:
    global _SERVER

    if "--server-only" in sys.argv:
        from server.main import main as run_server

        run_server()
        return 0

    if _alive(_PORT):
        # Another copy owns the port: bring that instance's window forward and
        # leave this one alone (no second server, no browser tab).
        _signal_show()
        time.sleep(0.4)
        return 0

    import uvicorn

    from server.main import app as fastapi_app

    config = uvicorn.Config(
        fastapi_app,
        host="0.0.0.0",
        port=_PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    _SERVER = server

    if not _menu_available() or os.environ.get("DESKGADGET_HEADLESS") == "1":
        server.run()
        return 0

    worker = threading.Thread(target=server.run, name="deskgadget-http", daemon=True)
    worker.start()

    deadline = time.time() + 10.0
    while time.time() < deadline:
        if _alive(_PORT):
            break
        if not worker.is_alive():
            break
        time.sleep(0.15)

    try:
        return _run_app(server)
    finally:
        server.should_exit = True
        worker.join(3.0)


if __name__ == "__main__":
    raise SystemExit(main())
