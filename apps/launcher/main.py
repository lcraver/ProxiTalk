import app_manager
from interfaces import AppBase
import time

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.display_queue = context["display_queue"]
        self.selection = 0
        self.app_count = 0
        self.valid_apps = []

    def start(self):
        print("[Launcher] Started")
        
        x = 1
        self.selection = 0
        self.drawAllApps()
        
    def drawAllApps(self):
        self.display_queue.put(("clear_base_area", 0, 0, 128, 64))

        icons = []
        for app in self.get_valid_apps():
            icons.append(app)

        self.app_count = len(icons)

        if self.app_count == 0:
            return

        # Assume consistent icon size
        test_icon = icons[0].get("icon_normal") or icons[0].get("icon_selected")
        icon_w, icon_h = test_icon.size
        padding = 4

        # Dynamically calculate best number of columns
        max_cols = max(1, 128 // (icon_w + padding))
        cols = min(self.app_count, max_cols)
        rows = (self.app_count + cols - 1) // cols  # ceil division

        total_grid_w = cols * (icon_w + padding) - padding
        total_grid_h = rows * (icon_h + padding) - padding

        x_offset = (128 - total_grid_w) // 2
        y_offset = (64 - total_grid_h) // 2

        for index, app in enumerate(icons):
            col = index % cols
            row = index // cols

            x = x_offset + col * (icon_w + padding)
            y = y_offset + row * (icon_h + padding)

            self.draw_app(index, app, x, y)

    def draw_app(self, index, app, x, y):
        if index == self.selection:
            icon = app.get("icon_selected")
        else:
            icon = app.get("icon_normal")

        if icon:
            self.display_queue.put(("draw_base_image", icon, x, y))


    def update(self):
        pass
    
    def onkeyup(self, keycode):
        if keycode == "KEY_LEFT":
            self.selection = (self.selection - 1) % self.app_count
            self.drawAllApps()
        elif keycode == "KEY_RIGHT":
            self.selection = (self.selection + 1) % self.app_count
            self.drawAllApps()
        elif keycode == "KEY_ENTER":
            if self.app_count > 0:
                # Swap to the selected app
                selected_app = self.get_selected_app()
                if selected_app:
                    name = selected_app['name']
                    self.context["app_manager"].swap_app_async(
                        "launcher", name, update_rate_hz=20.0, delay=0.1
                    )
            else:
                print("[Launcher] No apps to launch")
                
    def get_valid_apps(self):
        
        if self.valid_apps and self.valid_apps.count > 0:
            return self.valid_apps
        
        valid_apps = []
        for app in self.context["apps"]["all"]:
            if app['metadata']['type'].lower() == "overlay":
                continue
            if app['name'].lower() == "launcher":
                continue
            valid_apps.append(app)
        return valid_apps
                
    def get_selected_app(self):
        valid_apps = self.get_valid_apps()
        if 0 <= self.selection < len(valid_apps):
            return valid_apps[self.selection]
        return None

    def stop(self):
        print("[Launcher] Stopped")
