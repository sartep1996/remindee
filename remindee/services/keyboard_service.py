from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal


class KeyboardService(QObject):
    """Watches for global key sequences typed anywhere on the system.

    Monitored sequences
    -------------------
    R→E→M→<space>→<space>   fires ``quick_note_triggered``
    N→O→T→<space>→<space>   fires ``note_triggered``

    Runs pynput's Listener in a daemon thread so Qt's event loop is never
    blocked.  Qt auto-promotes the cross-thread ``emit`` to QueuedConnection,
    so the connected slot always executes on the main thread.

    macOS note: the process needs Input Monitoring (or Accessibility) access in
    System Settings → Privacy & Security.  Without it the listener fails
    gracefully and prints a hint to the console.
    """

    quick_note_triggered = Signal()
    note_triggered = Signal()

    _SEQ: list[str] = ["r", "e", "m", " ", " "]
    _NOTE_SEQ: list[str] = ["n", "o", "t", " ", " "]

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # Each entry: [expected_sequence, current_buffer, signal_to_emit]
        # Buffers are mutable lists so they can be updated in-place.
        self._sequences: list[tuple[list[str], list[str], Signal]] = [
            (self._SEQ, [], self.quick_note_triggered),
            (self._NOTE_SEQ, [], self.note_triggered),
        ]
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
                # Modifier, arrow, function key — reset all buffers
                for _seq, buf, _sig in self._sequences:
                    buf.clear()
                return

            for seq, buf, signal in self._sequences:
                expected = seq[len(buf)]
                if ch == expected:
                    buf.append(ch)
                    if len(buf) == len(seq):
                        buf.clear()
                        signal.emit()
                else:
                    buf.clear()
                    if ch == seq[0]:
                        buf.append(ch)
        except Exception:
            for _seq, buf, _sig in self._sequences:
                buf.clear()
