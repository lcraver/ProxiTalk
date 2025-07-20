from interfaces import AppBase

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.display_queue = context["display_queue"]
        self.draw = context["drawing"]  # New region-based drawing system
        self.user_prefs = context.get("user_preferences")
        self.selection = 0
        self.all_apps = []
        self.all_overlays = []
        self.filtered_apps = []
        self.width = context["screen_width"]
        self.scroll_offset = 0
        self.max_visible_items = 8  # Number of apps visible at once
        
        # Tab system
        self.current_tab = 0  # 0 = Visibility, 1 = Pinned, 2 = Overlays
        self.tabs = ["Visibility", "Pinned", "Overlays"]
        
        # UI constants
        self.item_height = 6
        self.header_height = 6
        self.footer_height = 6
        
        # Performance optimization
        self.needs_redraw = True
        self.last_drawn_tab = -1
        self.last_drawn_selection = -1
        self.last_drawn_scroll = -1
        
        print("[App Settings] App initialized with hardware optimizations")
        print("[App Settings] - Batching enabled to eliminate line-by-line drawing on real hardware")
        print("[App Settings] - Region-based updates for minimal display transfers")
        
    def start(self):
        print("[App Settings] Started")
        self.load_apps()
        self.load_overlays()
        
        # Sync overlay states with preferences when starting
        app_manager = self.context.get("app_manager")
        if app_manager and hasattr(app_manager, 'sync_overlays_with_preferences'):
            app_manager.sync_overlays_with_preferences()
        
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
            is_pinned = self.user_prefs.is_app_pinned(app['name']) if self.user_prefs else False
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
        
    def load_overlays(self):
        """Load all overlay apps"""
        self.all_overlays = []
        
        # Get app manager to access overlay apps
        app_manager = self.context.get("app_manager")
        if not app_manager or not hasattr(app_manager, 'overlay_apps'):
            print("[App Settings] No app manager or overlay apps available")
            return
        
        # Load overlay information
        import os
        overlay_dir = self.context.get("OVERLAY_DIR")
        if not overlay_dir or not os.path.exists(overlay_dir):
            print("[App Settings] Overlay directory not found")
            return
            
        for overlay_name in app_manager.overlay_apps:
            # Load overlay metadata
            metadata_path = os.path.join(overlay_dir, overlay_name, "metadata.json")
            display_name = overlay_name
            
            if os.path.isfile(metadata_path):
                try:
                    import json
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                        display_name = metadata.get('name', overlay_name)
                except Exception as e:
                    print(f"[App Settings] Error loading metadata for {overlay_name}: {e}")
            
            # Check if overlay is disabled in preferences
            is_disabled = self.user_prefs.is_overlay_disabled(overlay_name) if self.user_prefs else False
            
            # Also check current running state to ensure consistency
            is_currently_running = app_manager.is_app_running(overlay_name)
            
            # If preferences say disabled but overlay is running, or vice versa, log the inconsistency
            if is_disabled and is_currently_running:
                print(f"[App Settings] Warning: Overlay {overlay_name} is disabled in preferences but currently running")
            elif not is_disabled and not is_currently_running:
                print(f"[App Settings] Warning: Overlay {overlay_name} is enabled in preferences but not running")
            
            overlay_info = {
                'name': overlay_name,
                'display_name': display_name,
                'disabled': is_disabled
            }
            self.all_overlays.append(overlay_info)
        
        # Sort alphabetically by display name
        self.all_overlays.sort(key=lambda x: x['display_name'].lower())
        
    def draw_interface(self):
        """Draw the main interface using region-based updates with hardware optimization"""
        # Use batching for optimal hardware performance
        self.draw["begin_batch"]()
        
        try:
            self.draw["clear_screen"]()
            
            # Draw all components (will be batched for single hardware update)
            self.draw_header()
            self.draw_app_list()
            self.draw_footer()
            
            # Update tracking variables
            self.last_drawn_tab = self.current_tab
            self.last_drawn_selection = self.selection
            self.last_drawn_scroll = self.scroll_offset
        finally:
            # Execute all drawing operations at once
            self.draw["end_batch"]()
        
    def draw_header(self):
        """Draw the header with title and tab navigation using region updates"""
        font_small = self.context["fonts"]["small"]
        
        # Clear and draw white background for header
        self.draw["clear_area"](0, 0, 128, self.header_height)
        self.draw["draw_area"](0, 0, 128, self.header_height, 255)
        
        # Current tab title
        current_tab_name = self.tabs[self.current_tab]
        title = f"App {current_tab_name} Settings"
        
        # Calculate positions
        title_width = self.context["get_text_size"](title, font_small)[0]
        title_x = (128 - title_width) // 2
        
        # Draw navigation arrows
        if self.current_tab > 0:
            self.draw["draw_text"]("[", 2, 1, font_small, 0)
        else:
            self.draw["draw_text"]("|", 2, 1, font_small, 0)
        if self.current_tab < len(self.tabs) - 1:
            self.draw["draw_text"]("]", 120, 1, font_small, 0)
        else:
            self.draw["draw_text"]("|", 120, 1, font_small, 0)
        
        # Draw title
        self.draw["draw_text"](title, title_x, 1, font_small, 0)
        
    def draw_app_list(self):
        """Draw the scrollable list of apps or overlays using region updates with hardware optimization"""
        # Note: Batching is handled by parent draw_interface() method - no nested batching needed
        
        # Choose the appropriate list based on current tab
        if self.current_tab == 2:  # Overlays tab
            current_list = self.all_overlays
        else:  # Apps tabs
            current_list = self.filtered_apps
            
        # Clear the app list area
        list_y = self.header_height + 1
        list_height = 64 - self.header_height - self.footer_height - 2
        self.draw["clear_area"](0, list_y, 128, list_height)
            
        if not current_list:
            # Show appropriate "No items found" message
            font_small = self.context["fonts"]["small"]
            if self.current_tab == 2:
                msg = "No overlays found"
            else:
                msg = "No apps found"
            msg_width = self.context["get_text_size"](msg, font_small)[0]
            msg_x = (128 - msg_width) // 2
            msg_y = self.header_height + 20
            self.draw["draw_text"](msg, msg_x, msg_y, font_small)
            return
            
        # Calculate visible range
        start_idx = self.scroll_offset
        end_idx = min(start_idx + self.max_visible_items, len(current_list))
        
        # Draw each visible item (all will be batched for single hardware update)
        for i in range(start_idx, end_idx):
            item = current_list[i]
            y_pos = self.header_height + 1 + (i - start_idx) * self.item_height
            
            # Highlight selected item
            if i == self.selection:
                self.draw["draw_area"](0, y_pos, self.width - 5, self.item_height, 255)
                text_color = 0  # Black text on white background
            else:
                text_color = 255  # White text on black background
                
            # Draw item name
            font_small = self.context["fonts"]["small"]
            item_name = item['display_name']
            
            # Truncate name if too long
            max_name_width = 80
            if self.context["get_text_size"](item_name, font_small)[0] > max_name_width:
                while len(item_name) > 1 and self.context["get_text_size"](item_name + "...", font_small)[0] > max_name_width:
                    item_name = item_name[:-1]
                item_name += "..."
            
            self.draw["draw_text"](item_name, 2, y_pos+1, font_small, text_color)
            
            # Draw status based on current tab
            if self.current_tab == 0:  # Visibility tab
                status = "Hidden" if item['hidden'] else "Visible"
            elif self.current_tab == 1:  # Pinned tab
                status = "Pinned" if item['pinned'] else "Not Pinned"
            else:  # Overlays tab
                # Show both disabled state and running state for overlays
                if item['disabled']:
                    status = "Disabled"
                else:
                    # Check if the overlay is actually running
                    app_manager = self.context.get("app_manager")
                    is_running = app_manager.is_app_running(item['name']) if app_manager else False
                    status = "Running" if is_running else "Stopped"
                
            status_width = self.context["get_text_size"](status, font_small)[0]
            status_x = 128 - status_width - 5
            self.draw["draw_text"](status, status_x, y_pos+1, font_small, text_color)
            
        # Draw scroll indicators if needed
        if len(current_list) > self.max_visible_items:
            self.draw_scroll_indicators()
            
    def draw_scroll_indicators(self):
        """Draw scroll indicators using region updates"""
        # Choose the appropriate list based on current tab
        if self.current_tab == 2:  # Overlays tab
            current_list = self.all_overlays
        else:  # Apps tabs
            current_list = self.filtered_apps
            
        if len(current_list) <= self.max_visible_items:
            return  # No need for scrollbar if all items fit
            
        # Calculate scrollbar dimensions
        scrollbar_x = 128 - 3  # Position at right edge
        scrollbar_top = self.header_height + 1
        scrollbar_bottom = 64 - self.footer_height - 1 - 2 # Leave 2px padding at bottom and 1px at the top
        scrollbar_height = scrollbar_bottom - scrollbar_top
        
        # Calculate scroll position
        max_scroll = max(0, len(current_list) - self.max_visible_items)
        if max_scroll > 0:
            # Calculate the position of the scroll indicator
            scroll_ratio = self.scroll_offset / max_scroll
            
            # Calculate indicator position and size
            indicator_height = max(2, scrollbar_height // 6)  # At least 2px tall
            usable_height = scrollbar_height - indicator_height
            indicator_y = scrollbar_top + int(scroll_ratio * usable_height)
            
            # Draw scrollbar background track (thin white line)
            self.draw["draw_area"](scrollbar_x + 2, scrollbar_top, 1, scrollbar_height, 255)
            
            # Draw scroll indicator (filled rectangle)
            self.draw["draw_area"](scrollbar_x, indicator_y, 3, indicator_height, 255)
            
    def draw_footer(self):
        """Draw footer with instructions using region updates"""
        font_small = self.context["fonts"]["small"]
        footer_y = 64 - self.footer_height
        
        # Clear and draw white background for footer
        self.draw["clear_area"](0, footer_y, 128, self.footer_height)
        self.draw["draw_area"](0, footer_y, 128, self.footer_height, 255)
        
        # Instructions based on current tab
        if self.current_tab == 0:  # Visibility tab
            instructions = "Up/Down: Select  Space: Toggle"
        elif self.current_tab == 1:  # Pinned tab
            instructions = "Up/Down: Select  Space: Toggle"
        else:  # Overlays tab
            instructions = "Up/Down: Select  Space: Toggle"

        inst_width = self.context["get_text_size"](instructions, font_small)[0]
        
        # If instructions are too long, use shorter version
        if inst_width > 126:
            if self.current_tab == 0:
                instructions = "↑↓: Select  Space: Toggle  ←→: Tab"
            elif self.current_tab == 1:
                instructions = "↑↓: Select  Space: Pin  ←→: Tab"
            else:  # Overlays tab
                instructions = "↑↓: Select  Space: Toggle  T: Debug"
            inst_width = self.context["get_text_size"](instructions, font_small)[0]
            
        inst_x = (128 - inst_width) // 2
        self.draw["draw_text"](instructions, inst_x, footer_y + 1, font_small, 0)
        
    def draw_single_item(self, item_index):
        """Efficiently redraw a single item in the list with hardware optimization"""
        # Use batching even for single items to ensure optimal hardware performance
        self.draw["begin_batch"]()
        
        try:
            # Choose the appropriate list based on current tab
            if self.current_tab == 2:  # Overlays tab
                current_list = self.all_overlays
            else:  # Apps tabs
                current_list = self.filtered_apps
                
            if not current_list or item_index >= len(current_list):
                return
                
            # Check if item is currently visible
            start_idx = self.scroll_offset
            end_idx = min(start_idx + self.max_visible_items, len(current_list))
            
            if item_index < start_idx or item_index >= end_idx:
                return  # Item not visible, no need to redraw
                
            # Calculate position
            visible_index = item_index - start_idx
            y_pos = self.header_height + 1 + visible_index * self.item_height
            
            # Clear the item area
            self.draw["clear_area"](0, y_pos, self.width - 4, self.item_height)
            
            # Redraw the item
            item = current_list[item_index]
            
            # Highlight selected item
            if item_index == self.selection:
                self.draw["draw_area"](0, y_pos, self.width - 4, self.item_height, 255)
                text_color = 0  # Black text on white background
            else:
                text_color = 255  # White text on black background
                
            # Draw item name
            font_small = self.context["fonts"]["small"]
            item_name = item['display_name']
            
            # Truncate name if too long
            max_name_width = 80
            if self.context["get_text_size"](item_name, font_small)[0] > max_name_width:
                while len(item_name) > 1 and self.context["get_text_size"](item_name + "...", font_small)[0] > max_name_width:
                    item_name = item_name[:-1]
                item_name += "..."
            
            self.draw["draw_text"](item_name, 2, y_pos+1, font_small, text_color)
            
            # Draw status based on current tab
            if self.current_tab == 0:  # Visibility tab
                status = "Hidden" if item['hidden'] else "Visible"
            elif self.current_tab == 1:  # Pinned tab
                status = "Pinned" if item['pinned'] else "Not Pinned"
            else:  # Overlays tab
                # Show both disabled state and running state for overlays
                if item['disabled']:
                    status = "Disabled"
                else:
                    # Check if the overlay is actually running
                    app_manager = self.context.get("app_manager")
                    is_running = app_manager.is_app_running(item['name']) if app_manager else False
                    status = "Running" if is_running else "Stopped"
                
            status_width = self.context["get_text_size"](status, font_small)[0]
            status_x = 128 - status_width - 5
            self.draw["draw_text"](status, status_x, y_pos+1, font_small, text_color)
        finally:
            # Execute all operations at once for hardware optimization
            self.draw["end_batch"]()

    def update_scroll(self):
        """Update scroll offset to keep selection visible"""
        # Choose the appropriate list based on current tab
        if self.current_tab == 2:  # Overlays tab
            current_list = self.all_overlays
        else:  # Apps tabs
            current_list = self.filtered_apps
            
        if self.selection < self.scroll_offset:
            self.scroll_offset = self.selection
        elif self.selection >= self.scroll_offset + self.max_visible_items:
            self.scroll_offset = self.selection - self.max_visible_items + 1
            
    def toggle_app_visibility(self):
        """Toggle visibility, pinned status, or overlay status based on current tab"""
        if self.current_tab == 2:  # Overlays tab
            self.toggle_overlay_status()
        else:  # Apps tabs
            self.toggle_app_status()
            
    def toggle_app_status(self):
        """Toggle visibility or pinned status of the selected app"""
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
                    
                    # Use selective redraw instead of full redraw
                    self.draw_single_item(self.selection)
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
                    
                    # Use selective redraw instead of full redraw
                    self.draw_single_item(self.selection)
                else:
                    print(f"[App Settings] Failed to toggle pinned status for {app_name}")
    
    def toggle_overlay_status(self):
        """Toggle enabled/disabled status of the selected overlay"""
        if not self.all_overlays or self.selection >= len(self.all_overlays):
            return
            
        overlay = self.all_overlays[self.selection]
        overlay_name = overlay['name']
        
        if self.user_prefs:
            # Toggle overlay enabled status in preferences
            success = self.user_prefs.toggle_overlay_enabled(overlay_name)
            if success:
                # Update local state
                overlay['disabled'] = not overlay['disabled']
                print(f"[App Settings] Toggled {overlay_name} status to {'disabled' if overlay['disabled'] else 'enabled'}")
                
                # Start or stop the overlay based on new status
                app_manager = self.context.get("app_manager")
                if app_manager:
                    is_currently_running = app_manager.is_app_running(overlay_name)
                    
                    if overlay['disabled']:
                        # Stop the overlay if it's running
                        if is_currently_running:
                            if app_manager.stop_app(overlay_name):
                                print(f"[App Settings] Stopped overlay: {overlay_name}")
                            else:
                                print(f"[App Settings] Failed to stop overlay: {overlay_name}")
                        else:
                            print(f"[App Settings] Overlay {overlay_name} was already stopped")
                    else:
                        # Start the overlay if it's not running
                        if not is_currently_running:
                            if app_manager.start_app(overlay_name, update_rate_hz=20.0):
                                print(f"[App Settings] Started overlay: {overlay_name}")
                            else:
                                print(f"[App Settings] Failed to start overlay: {overlay_name}")
                        else:
                            print(f"[App Settings] Overlay {overlay_name} was already running")
                else:
                    print("[App Settings] No app manager available")
                
                # Use selective redraw instead of full redraw
                self.draw_single_item(self.selection)
            else:
                print(f"[App Settings] Failed to toggle status for overlay {overlay_name}")
                
    def update(self):
        # Smart redraw - only update what changed
        if self.needs_redraw:
            # Check what specifically changed to optimize redraws
            tab_changed = (self.current_tab != self.last_drawn_tab)
            selection_changed = (self.selection != self.last_drawn_selection)
            scroll_changed = (self.scroll_offset != self.last_drawn_scroll)
            
            if tab_changed:
                # Full redraw needed when tab changes
                self.draw_interface()
            elif selection_changed or scroll_changed:
                # Use batching for partial updates too
                self.draw["begin_batch"]()
                try:
                    # Only redraw the app list area when selection/scroll changes
                    self.draw_app_list()
                finally:
                    self.draw["end_batch"]()
                # Update tracking variables
                self.last_drawn_selection = self.selection
                self.last_drawn_scroll = self.scroll_offset
            else:
                # Full redraw for other changes
                self.draw_interface()
                
            self.needs_redraw = False
        
    def onkeyup(self, keycode):        
        if keycode == "KEY_UP" or keycode == "KEY_W":
            # Choose the appropriate list based on current tab
            if self.current_tab == 2:  # Overlays tab
                current_list = self.all_overlays
            else:  # Apps tabs
                current_list = self.filtered_apps
                
            if current_list and self.selection > 0:
                old_selection = self.selection
                self.selection -= 1
                self.update_scroll()
                
                # Smart redraw - only redraw the two affected items if no scrolling occurred
                if self.scroll_offset == self.last_drawn_scroll:
                    self.draw_single_item(old_selection)
                    self.draw_single_item(self.selection)
                    self.last_drawn_selection = self.selection
                else:
                    # Scrolling occurred, need to redraw the whole list
                    self.needs_redraw = True
                
        elif keycode == "KEY_DOWN" or keycode == "KEY_S":
            # Choose the appropriate list based on current tab
            if self.current_tab == 2:  # Overlays tab
                current_list = self.all_overlays
            else:  # Apps tabs
                current_list = self.filtered_apps
                
            if current_list and self.selection < len(current_list) - 1:
                old_selection = self.selection
                self.selection += 1
                self.update_scroll()
                
                # Smart redraw - only redraw the two affected items if no scrolling occurred
                if self.scroll_offset == self.last_drawn_scroll:
                    self.draw_single_item(old_selection)
                    self.draw_single_item(self.selection)
                    self.last_drawn_selection = self.selection
                else:
                    # Scrolling occurred, need to redraw the whole list
                    self.needs_redraw = True
                
        elif keycode == "KEY_LEFT" or keycode == "KEY_A":
            self.switch_tab(-1)
            
        elif keycode == "KEY_RIGHT" or keycode == "KEY_D":
            self.switch_tab(1)
                
        elif keycode == "KEY_SPACE" or keycode == "KEY_ENTER":
            # Toggle operations handle their own selective redraws
            self.toggle_app_visibility()
            
        elif keycode == "KEY_ESC" or keycode == "KEY_BACKSPACE":
            # Exit to launcher
            self.context["app_manager"].swap_app_async(
                "app_settings", "launcher", update_rate_hz=20.0, delay=0.1
            )
            
        elif keycode == "KEY_R":
            # Refresh app list and sync overlays
            self.load_apps()
            self.load_overlays()
            
            # Also sync overlay states with preferences
            app_manager = self.context.get("app_manager")
            if app_manager and hasattr(app_manager, 'sync_overlays_with_preferences'):
                app_manager.sync_overlays_with_preferences()
            
            self.selection = 0
            self.scroll_offset = 0
            self.needs_redraw = True
            
        elif keycode == "KEY_T":
            # Debug: Print overlay status information
            if self.current_tab == 2:  # Only on overlays tab
                app_manager = self.context.get("app_manager")
                if app_manager:
                    print("\n[App Settings] Overlay Status Debug:")
                    for overlay in self.all_overlays:
                        overlay_name = overlay['name']
                        is_running = app_manager.is_app_running(overlay_name)
                        is_disabled = overlay['disabled']
                        print(f"  {overlay_name}: disabled={is_disabled}, running={is_running}")
                    
                    print(f"\nApps receiving events: {app_manager.get_event_receiving_apps()}")
                    print("") # Empty line for readability
            
    def switch_tab(self, direction):
        """Switch to next or previous tab"""
        new_tab = self.current_tab + direction
        if 0 <= new_tab < len(self.tabs):
            self.current_tab = new_tab
            # Reset selection and scroll when switching tabs
            self.selection = 0
            self.scroll_offset = 0
            # Mark for redraw to update the interface
            self.needs_redraw = True
            
    def stop(self):
        print("[App Settings] Stopped")
