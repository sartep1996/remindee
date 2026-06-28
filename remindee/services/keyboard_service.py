from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal


class KeyboardService(QObject):
    """Watches for R→E→M→<space>→<space> typed anywhere on the system.

    Runs pynput's Listener in a daemon thread so Qt's event loop is never
    blocked.  Qt auto-promotes the cross-thread ``emit`` to QueuedConnection,
    so the connected slot always executes on the main thread.

    macOS note: the process needs Input Monitoring (or Accessibility) access in
    System Settings → Privacy & Security.  Without it the listener fails
    gracefully and prints a hint to the console.
    """

    quick_note_triggered = Signal()

    _SEQ: list[str] = ["r", "e", "m", " ", " "]

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._buf: list[str] = []
        self._listener = None
        self._thread: threading.Thread | None = None
        self._active = False

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._active = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="kbd-listener"
        )
        self._thread.start()

    def stop(self) -> None:
        self._active = False
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass

    # ── Background listener ──────────────────────────────────────────────────

    def _run(self) -> None:
        try:
            from pynput import keyboard
            with keyboard.Listener(on_press=self._on_press) as listener:
                self._listener = listener
                listener.join()
        except Exception as exc:
            print(f"[KeyboardService] listener failed to start: {exc}")
            print(
                "  macOS: grant Input Monitoring (or Accessibility) access in\n"
                "  System Settings → Privacy & Security → Input Monitoring"
            )

    def _on_press(self, key) -> None:
        if not self._active:
            return
        try:
            from pynput import keyboard as kb
            if key == kb.Key.space:
                ch = " "
            elif hasattr(key, "char") and key.char:
                ch = key.char.lower()
            else:
                # Modifier, arrow, function key — reset sequence
                self._buf.clear()
                return

            expected = self._SEQ[len(self._buf)]
            if ch == expected:
                self._buf.append(ch)
                if len(self._buf) == len(self._SEQ):
                    self._buf.clear()
                    self.quick_note_triggered.emit()
            else:
                self._buf.clear()
                if ch == self._SEQ[0]:
                    self._buf.append(ch)
        except Exception:
            self._buf.clear()
