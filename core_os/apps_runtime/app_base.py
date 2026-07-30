from __future__ import annotations


class AppBase:
    def __init__(self, context):
        """
        context: dict containing shared functions and state (e.g., display, TTS, etc.)
        """
        self.context = context

    def start(self):
        """
        Run when the app starts.
        """
        pass

    def update(self):
        """
        Called 1/20th of a second (20Hz).
        """
        pass

    def onkeydown(self, keycode):
        """
        Called when a key is pressed down.
        """
        pass

    def onkeyup(self, keycode):
        """
        Called when a key is released.
        """
        pass

    def stop(self):
        """
        Run when the app is stopped.
        """
        pass


__all__ = ["AppBase"]
