"""Voice Monitor -- a separate window (View menu toggle in the emulator)
listing every currently active synth voice and its state. The device-map
speaker placeholder only has room for a one-line summary (see
core_os/core/debug_log.py and synth/player.py's _mix_chunk); this reads the
same registry's per-voice detail instead, so "how many voices and what are
they doing" is actually legible.

Runs its own Tk mainloop on a dedicated thread: pygame already owns the
main window/thread (see EmulatedDisplay._run_pygame_loop), and each
tkinter.Tk() call creates its own Tcl interpreter, so a second one on its
own thread doesn't contend with pygame's -- the same approach
EmulatedDisplay._copy_selection_to_clipboard already uses for one-shot
clipboard access, just kept alive here instead of torn down immediately."""

from __future__ import annotations

import threading
from typing import Callable, Optional

from core_os.core import debug_log

_POLL_MS = 150
_SYNTH_KEY = "synth"


class VoiceMonitorWindow:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._root = None

    def is_open(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def open(self, on_close: Optional[Callable[[], None]] = None) -> None:
        if self.is_open():
            return
        self._thread = threading.Thread(target=self._run, args=(on_close,), daemon=True)
        self._thread.start()

    def close(self) -> None:
        root = self._root
        if root is not None:
            try:
                root.after(0, root.destroy)
            except Exception:
                pass

    def _run(self, on_close: Optional[Callable[[], None]]) -> None:
        import tkinter as tk

        root = tk.Tk()
        self._root = root
        root.title("Voice Monitor")
        root.geometry("360x240")
        root.configure(bg="#1e1e1e")
        root.protocol("WM_DELETE_WINDOW", root.destroy)

        header = tk.Label(
            root, text="Voices: 0", font=("Consolas", 11, "bold"),
            anchor="w", bg="#1e1e1e", fg="#33ff33",
        )
        header.pack(fill="x", padx=8, pady=(8, 4))

        body = tk.Text(root, font=("Consolas", 10), state="disabled", bg="#1e1e1e", fg="#33ff33", bd=0)
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        def refresh() -> None:
            if not root.winfo_exists():
                return
            voices = debug_log.get_voice_detail().get(_SYNTH_KEY, [])
            header.config(text=f"Voices: {len(voices)}")
            body.config(state="normal")
            body.delete("1.0", "end")
            if voices:
                for i, voice in enumerate(voices, start=1):
                    body.insert("end", f"{i}. {voice['label']}  [{voice['state']}]\n")
            else:
                body.insert("end", "(silent)\n")
            body.config(state="disabled")
            root.after(_POLL_MS, refresh)

        refresh()
        root.mainloop()
        self._root = None
        if on_close is not None:
            on_close()


__all__ = ["VoiceMonitorWindow"]
