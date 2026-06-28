"""macOS NSVisualEffectView vibrancy. No-op on all other platforms."""
from __future__ import annotations

import sys


def enable_mac_vibrancy(window, dark: bool = False) -> bool:
    """
    Wrap *window*'s native NSView inside an NSVisualEffectView so that the
    system compositor blurs the desktop behind the Qt window.

    Call this AFTER window.show() (and QApplication.processEvents()) so the
    native NSWindow exists.  Returns True on success, False if not on macOS or
    PyObjC is unavailable.

    How it works
    ────────────
    Qt on macOS sets QNSView (its NSView subclass) as NSWindow.contentView.
    We create an NSVisualEffectView, move QNSView inside it as a subview, then
    promote NSVisualEffectView to be the new contentView:

        NSWindow
        └─ NSVisualEffectView  ← new contentView (system blur layer)
           └─ QNSView          ← Qt renders here; alpha=0 areas reveal blur
    """
    if sys.platform != "darwin":
        return False

    try:
        import ctypes
        import objc
        from AppKit import (
            NSVisualEffectView,
            NSVisualEffectBlendingModeBehindWindow,
            NSVisualEffectStateActive,
        )
    except ImportError:
        return False

    try:
        ptr = int(window.winId())
        if ptr == 0:
            return False

        qt_view = objc.objc_object(c_void_p=ctypes.c_void_p(ptr))
        ns_window = qt_view.window()
        if ns_window is None:
            return False

        # NSVisualEffectMaterialWindowBackground = 12
        # Gives the standard macOS frosted-glass look (Finder, ChatGPT-style).
        effect = NSVisualEffectView.alloc().initWithFrame_(qt_view.bounds())
        effect.setMaterial_(12)
        effect.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        effect.setState_(NSVisualEffectStateActive)
        # NSViewWidthSizable (2) | NSViewHeightSizable (16) = 18
        effect.setAutoresizingMask_(18)

        if dark:
            from AppKit import NSAppearance
            dark_app = NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua")
            if dark_app is not None:
                effect.setAppearance_(dark_app)

        # Keep Qt's view autoresizing so it fills the effect view
        qt_view.setAutoresizingMask_(18)

        # Move Qt's native view inside the effect view, then promote
        # effect view to be the NSWindow's content view.
        effect.addSubview_(qt_view)
        ns_window.setContentView_(effect)

        return True

    except Exception:
        return False
