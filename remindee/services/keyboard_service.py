from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal


_LISTENER_SCRIPT = Path(__file__).parent / "keyboard_listener_process.py"


class KeyboardService(QObject):
    """Watches for global key sequences typed anywhere on the system.

    Monitored sequences
    -------------------
    R→E→M→<space>→<space>   fires ``quick_note_triggered``
    N→O→T→<space>→<space>   fires ``note_triggered``

    The pynput listener runs inside a **child process** (not just a thread)
    so that if pynput calls a macOS API that requires the main thread
    (e.g. TSMGetInputSourceProperty on macOS 26+) and raises SIGTRAP, only
    the child process dies — the main application is unaffected.

    Qt auto-promotes the cross-thread ``emit`` to QueuedConnection so the
    connected slot always executes on the main thread.
    """

    quick_note_triggered = Signal()
    note_triggered = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._active = False
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._active = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="kbd-listener"
        )
        self._thread.start()

    def stop(self) -> None:
        self._active = False
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass

    # ── Background reader ────────────────────────────────────────────────────

    def _run(self) -> None:
        try:
            self._proc = subprocess.Popen(
                [sys.executable, str(_LISTENER_SCRIPT)],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
            for line in self._proc.stdout:  # type: ignore[union-attr]
                if not self._active:
                    break
                line = line.strip()
                if line == "quick_note":
                    self.quick_note_triggered.emit()
                elif line == "note":
                    self.note_triggered.emit()
        except Exception as exc:
            print(f"[KeyboardService] subprocess failed: {exc}")
            print(
                "  macOS: grant Input Monitoring (or Accessibility) access in\n"
                "  System Settings → Privacy & Security → Input Monitoring"
            )
