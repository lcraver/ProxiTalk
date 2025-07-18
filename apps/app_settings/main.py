from interfaces import AppBase

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.display_queue = context["display_queue"]
        self.user_prefs = context.get("user_preferences")
        self.selection = 0
        self.all_apps = []
        self.filtered_apps = []
        self.width = context["screen_width"]
        self.scroll_offset = 0
        self.max_visible_items = 7  # Number of apps visible at once
        
        # Tab system
        self.current_tab = 0  # 0 = Visibility, 1 = Pinned
        self.tabs = ["Visibility", "Pinned"]
        
        # UI constants
        self.item_height = 7
        self.header_height = 6
        self.footer_height = 6
        print("[App Settings] App initialized")
        
    def start(self):
        print("[App Settings] Started")
        self.load_apps()
        self.draw_interface()
        
    def load_apps(self):
        """Load all launchable apps (excluding overlays, launcher, and this app)"""
        self.all_apps = []
        
        for app in self.context["apps"]["all"]:
            # Skip overlay apps, launcher, and this app
            if (app['metadata']['type'].lower() == "overlay" or 
                app['name'].lower() == "launcher" or 
                app['name'].lower() == "app_settings"):
                continue
            
            # Add visibility and pinned status
            is_hidden = self.user_prefs.is_app_hidden(app['name']) if self.user_prefs else False
            is_pinned = self.user_prefs.get_preference(f"app_{app['name']}_pinned", False) if self.user_prefs else False
            app_info = {
                'name': app['name'],
                'display_name': app['metadata'].get('name', app['name']),
                'hidden': is_hidden,
                'pinned': is_pinned
            }
            self.all_apps.append(app_info)
        
        # Sort alphabetically by display name
        self.all_apps.sort(key=lambda x: x['display_name'].lower())
        self.filtered_apps = self.all_apps[:]
        
    def draw_interface(self):
        """Draw the main interface"""
        self.display_queue.put(("clear_base",))
        
        # Draw header
        self.draw_header()
        
        # Draw app list
        self.draw_app_list()
        
        # Draw footer with instructions
        self.draw_footer()
        
    def draw_header(self):
        """Draw the header with title and tab navigation"""
        font_small = self.context["fonts"]["small"]
        
        # Draw white background for header
        self.display_queue.put(("draw_base_area", 0, 0, 128, self.header_height - 1, 255))
        
        # Current tab title
        current_tab_name = self.tabs[self.current_tab]
        title = f"App {current_tab_name} Settings"
        
        # Calculate positions
        title_width = self.context["get_text_size"](title, font_small)[0]
        title_x = (128 - title_width) // 2
        
        # Draw navigation arrows
        if self.current_tab > 0:
            self.display_queue.put(("draw_base_text", font_small, "[", 2, 0, 0))
        else:
            self.display_queue.put(("draw_base_text", font_small, "|", 2, 0, 0))
        if self.current_tab < len(self.tabs) - 1:
            self.display_queue.put(("draw_base_text", font_small, "]", 120, 0, 0))
        else:
            self.display_queue.put(("draw_base_text", font_small, "|", 120, 0, 0))
        
        # Draw title
        self.display_queue.put(("draw_base_text", font_small, title, title_x, 0, 0))
        
    def draw_app_list(self):
        """Draw the scrollable list of apps"""
        if not self.filtered_apps:
            # Show "No apps found" message
            font_small = self.context["fonts"]["small"]
            msg = "No apps found"
            msg_width = self.context["get_text_size"](msg, font_small)[0]
            msg_x = (128 - msg_width) // 2
            msg_y = self.header_height + 20
            self.display_queue.put(("draw_base_text", font_small, msg, msg_x, msg_y))
            return
            
        # Calculate visible range
        start_idx = self.scroll_offset
        end_idx = min(start_idx + self.max_visible_items, len(self.filtered_apps))
        
        # Draw each visible app
        for i in range(start_idx, end_idx):
            app = self.filtered_apps[i]
            y_pos = self.header_height + 1 + (i - start_idx) * self.item_height
            
            # Highlight selected item
            if i == self.selection:
                self.display_queue.put(("draw_base_area", 0, y_pos, self.width - 5, self.item_height-2, 255))
                text_color = 0  # Black text on white background
            else:
                text_color = 255  # White text on black background
                
            # Draw app name
            font_small = self.context["fonts"]["small"]
            app_name = app['display_name']
            
            # Truncate name if too long
            max_name_width = 80
            if self.context["get_text_size"](app_name, font_small)[0] > max_name_width:
                while len(app_name) > 1 and self.context["get_text_size"](app_name + "...", font_small)[0] > max_name_width:
                    app_name = app_name[:-1]
                app_name += "..."
            
            self.display_queue.put(("draw_base_text", font_small, app_name, 2, y_pos, text_color))
            
            # Draw visibility or pinned status based on current tab
            if self.current_tab == 0:  # Visibility tab
                status = "Hidden" if app['hidden'] else "Visible"
            else:  # Pinned tab
                status = "Pinned" if app['pinned'] else "Not Pinned"
                
            status_width = self.context["get_text_size"](status, font_small)[0]
            status_x = 128 - status_width - 2 - 3
            self.display_queue.put(("draw_base_text", font_small, status, status_x, y_pos, text_color))
            
        # Draw scroll indicators if needed
        if len(self.filtered_apps) > self.max_visible_items:
            self.draw_scroll_indicators()
            
    def draw_scroll_indicators(self):
        """Draw scroll indicators similar to discourse_chat"""
        if len(self.filtered_apps) <= self.max_visible_items:
            return  # No need for scrollbar if all items fit
            
        # Calculate scrollbar dimensions
        scrollbar_x = 128 - 3  # Position at right edge
        scrollbar_top = self.header_height + 1
        scrollbar_bottom = 64 - self.footer_height - 4
        scrollbar_height = scrollbar_bottom - scrollbar_top
        
        # Calculate scroll position
        max_scroll = max(0, len(self.filtered_apps) - self.max_visible_items)
        if max_scroll > 0:
            # Calculate the position of the scroll indicator
            scroll_ratio = self.scroll_offset / max_scroll
            
            # Calculate indicator position and size
            indicator_height = max(2, scrollbar_height // 6)  # At least 2px tall
            usable_height = scrollbar_height - indicator_height
            indicator_y = scrollbar_top + int(scroll_ratio * usable_height)
            
            # Draw scrollbar background track (thin white line)
            self.display_queue.put(("draw_base_area", scrollbar_x + 2, scrollbar_top, 1, scrollbar_height, 255))
            
            # Draw scroll indicator (filled rectangle)
            self.display_queue.put(("draw_base_area", scrollbar_x, indicator_y, 3, indicator_height, 255))
            
    def draw_footer(self):
        """Draw footer with instructions"""
        font_small = self.context["fonts"]["small"]
        footer_y = 64 - self.footer_height
        
        # Draw white background for footer
        self.display_queue.put(("draw_base_area", 0, footer_y, 128, self.footer_height, 255))
        
        # Instructions based on current tab
        if self.current_tab == 0:  # Visibility tab
            instructions = "Up/Down: Select  Space: Toggle"
        else:  # Pinned tab
            instructions = "Up/Down: Select  Space: Toggle"

        inst_width = self.context["get_text_size"](instructions, font_small)[0]
        
        # If instructions are too long, use shorter version
        if inst_width > 126:
            if self.current_tab == 0:
                instructions = "↑↓: Select  Space: Toggle  ←→: Tab"
            else:
                instructions = "↑↓: Select  Space: Pin  ←→: Tab"
            inst_width = self.context["get_text_size"](instructions, font_small)[0]
            
        inst_x = (128 - inst_width) // 2
        self.display_queue.put(("draw_base_text", font_small, instructions, inst_x, footer_y, 0))
        
    def update_scroll(self):
        """Update scroll offset to keep selection visible"""
        if self.selection < self.scroll_offset:
            self.scroll_offset = self.selection
        elif self.selection >= self.scroll_offset + self.max_visible_items:
            self.scroll_offset = self.selection - self.max_visible_items + 1
            
    def toggle_app_visibility(self):
        """Toggle visibility or pinned status of the selected app based on current tab"""
        if not self.filtered_apps or self.selection >= len(self.filtered_apps):
            return
            
        app = self.filtered_apps[self.selection]
        app_name = app['name']
        
        if self.user_prefs:
            if self.current_tab == 0:  # Visibility tab
                # Toggle visibility
                success = self.user_prefs.toggle_app_visibility(app_name)
                if success:
                    # Update local state
                    app['hidden'] = not app['hidden']
                    print(f"[App Settings] Toggled {app_name} visibility to {'hidden' if app['hidden'] else 'visible'}")
                    
                    # Refresh launcher if it's loaded
                    app_manager = self.context.get("app_manager")
                    if app_manager:
                        launcher_instance = app_manager.get_app_instance("launcher")
                        if launcher_instance and hasattr(launcher_instance, 'refresh_apps'):
                            launcher_instance.refresh_apps()
                            print("[App Settings] Refreshed launcher app list")
                    
                    # Redraw interface
                    self.draw_interface()
                else:
                    print(f"[App Settings] Failed to toggle visibility for {app_name}")
            else:  # Pinned tab
                # Toggle pinned status
                success = self.user_prefs.toggle_app_pinned(app_name)
                if success:
                    # Update local state
                    app['pinned'] = not app['pinned']
                    print(f"[App Settings] Toggled {app_name} pinned status to {'pinned' if app['pinned'] else 'unpinned'}")
                    
                    # Refresh launcher if it's loaded
                    app_manager = self.context.get("app_manager")
                    if app_manager:
                        launcher_instance = app_manager.get_app_instance("launcher")
                        if launcher_instance and hasattr(launcher_instance, 'refresh_apps'):
                            launcher_instance.refresh_apps()
                            print("[App Settings] Refreshed launcher app list")
                    
                    # Redraw interface
                    self.draw_interface()
                else:
                    print(f"[App Settings] Failed to toggle pinned status for {app_name}")
                
    def update(self):
        pass
        
    def onkeyup(self, keycode):
        if keycode == "KEY_UP" or keycode == "KEY_W":
            if self.filtered_apps and self.selection > 0:
                self.selection -= 1
                self.update_scroll()
                self.draw_interface()
                
        elif keycode == "KEY_DOWN" or keycode == "KEY_S":
            if self.filtered_apps and self.selection < len(self.filtered_apps) - 1:
                self.selection += 1
                self.update_scroll()
                self.draw_interface()
                
        elif keycode == "KEY_LEFT" or keycode == "KEY_A":
            self.switch_tab(-1)
            
        elif keycode == "KEY_RIGHT" or keycode == "KEY_D":
            self.switch_tab(1)
                
        elif keycode == "KEY_SPACE" or keycode == "KEY_ENTER":
            self.toggle_app_visibility()
            
        elif keycode == "KEY_ESC" or keycode == "KEY_BACKSPACE":
            # Exit to launcher
            self.context["app_manager"].swap_app_async(
                "app_settings", "launcher", update_rate_hz=20.0, delay=0.1
            )
            
        elif keycode == "KEY_R":
            # Refresh app list
            self.load_apps()
            self.selection = 0
            self.scroll_offset = 0
            self.draw_interface()
            
    def switch_tab(self, direction):
        """Switch to next or previous tab"""
        new_tab = self.current_tab + direction
        if 0 <= new_tab < len(self.tabs):
            self.current_tab = new_tab
            self.redraw_needed = True
            self.draw_interface()
            
    def stop(self):
        print("[App Settings] Stopped")
