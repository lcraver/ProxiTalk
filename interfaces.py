class AppBase:
    def __init__(self, context):
        """
        context: dict containing shared functions and state (e.g., display, TTS, etc.)
        """
        self.context = context

    def start(self):
        pass

    def update(self):
        pass
    
    def onkeydown(self, keycode):
        pass

    def onkeyup(self, keycode):
        pass
    
    def stop(self):
        pass
