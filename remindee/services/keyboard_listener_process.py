"""Standalone subprocess entry-point for the pynput global keyboard listener.

Run by KeyboardService as a child process so that if pynput crashes
(e.g. SIGTRAP from TSMGetInputSourceProperty on macOS 26+) only this
subprocess dies — the main application process is unaffected.

Protocol: one line to stdout per hotkey event.
  quick_note  →  "rem  " sequence recognised
  note        →  "not  " sequence recognised
"""
from __future__ import annotations

import sys

_SEQ_MAP = [
    (["r", "e", "m", " ", " "], "quick_note"),
    (["n", "o", "t", " ", " "], "note"),
]

# Mutable buffers kept as module-level list so on_press can update them
_buffers: list[list[str]] = [[] for _ in _SEQ_MAP]


def _on_press(key) -> None:
    try:
        from pynput import keyboard as kb
        if key == kb.Key.space:
            ch = " "
        elif hasattr(key, "char") and key.char:
            ch = key.char.lower()
        else:
            for buf in _buffers:
                buf.clear()
            return

        for (seq, name), buf in zip(_SEQ_MAP, _buffers):
            if ch == seq[len(buf)]:
                buf.append(ch)
                if len(buf) == len(seq):
                    buf.clear()
                    print(name, flush=True)
            else:
                buf.clear()
                if ch == seq[0]:
                    buf.append(ch)
    except Exception:
        for buf in _buffers:
            buf.clear()


if __name__ == "__main__":
    try:
        from pynput import keyboard
        with keyboard.Listener(on_press=_on_press) as listener:
            listener.join()
    except Exception as exc:
        print(f"ERROR:{exc}", file=sys.stderr, flush=True)
        sys.exit(1)
