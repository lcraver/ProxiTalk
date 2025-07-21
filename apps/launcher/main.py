import app_manager
from interfaces import AppBase
import time

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.selection = 0
        self.app_count = 0
        self.valid_apps = []
        self.user_prefs = context.get("user_preferences")
        
        # Pagination settings
        self.apps_per_page = 8  # Maximum apps to show per page
        self.current_page = 0
        self.total_pages = 0
        
        # Performance optimization - track what needs updating
        self.needs_redraw = True
        self.needs_full_redraw = True  # First time always full redraw
        self.last_page = -1
        self.last_selection = -1
        self.last_layout = None  # Track layout changes
        
        # Track drawn regions for efficient updates
        self.app_regions = {}  # {app_index: (x, y, width, height)}
        self.dots_region = None  # (x, y, width, height) for pagination dots

    def start(self):
        print("[Launcher] Started")
        
        # Load last selection from preferences if available
        if self.user_prefs:
            last_app_name = self.user_prefs.get_last_launched_app()
            if last_app_name:
                # Find the index of the last launched app
                valid_apps = self.get_valid_apps()
                for i, app in enumerate(valid_apps):
                    if app['name'] == last_app_name:
                        self.selection = i
                        # Calculate which page the selected app is on
                        self.current_page = i // self.apps_per_page
                        print(f"[Launcher] Auto-selected last app: {last_app_name} (index {i}, page {self.current_page})")
                        break
        
    def start(self):
        print("[Launcher] Started")
        
        # Load last selection from preferences if available
        if self.user_prefs:
            last_app_name = self.user_prefs.get_last_launched_app()
            if last_app_name:
                # Find the index of the last launched app
                valid_apps = self.get_valid_apps()
                for i, app in enumerate(valid_apps):
                    if app['name'] == last_app_name:
                        self.selection = i
                        # Calculate which page the selected app is on
                        self.current_page = i // self.apps_per_page
                        print(f"[Launcher] Auto-selected last app: {last_app_name} (index {i}, page {self.current_page})")
                        break
        
        # Initial full screen clear and draw
        self.needs_full_redraw = True
        self.drawAllApps()
        
    def drawAllApps(self):
        """Smart drawing that only updates changed regions"""
        all_apps = self.get_valid_apps()
        self.app_count = len(all_apps)

        if self.app_count == 0:
            if self.needs_full_redraw:
                self.context["drawing"]["begin_batch"]()
                self.context["drawing"]["clear_screen"]()
                self.context["drawing"]["end_batch"]()
                self.needs_full_redraw = False
            return

        # Calculate pagination
        self.total_pages = (self.app_count + self.apps_per_page - 1) // self.apps_per_page
        
        # Ensure current_page is valid
        if self.current_page >= self.total_pages:
            self.current_page = self.total_pages - 1
        if self.current_page < 0:
            self.current_page = 0

        # Get apps for current page
        start_index = self.current_page * self.apps_per_page
        end_index = min(start_index + self.apps_per_page, self.app_count)
        page_apps = all_apps[start_index:end_index]

        if not page_apps:
            return

        # Calculate layout
        current_layout = self.calculate_layout(page_apps)
        
        # Determine what needs updating
        page_changed = self.last_page != self.current_page
        selection_changed = self.last_selection != self.selection
        layout_changed = self.last_layout != current_layout
        
        # Full redraw if page changed or first time
        if self.needs_full_redraw or page_changed or layout_changed:
            self.context["drawing"]["begin_batch"]()
            self.context["drawing"]["clear_screen"]()
            
            self.app_regions.clear()
            self.dots_region = None
            
            # Draw pagination dots (if more than 1 page)
            if self.total_pages > 1:
                self.draw_pagination_dots()
            
            # Draw all apps for current page
            self.draw_all_page_apps(page_apps, start_index, current_layout)
            
            self.context["drawing"]["end_batch"]()
            self.needs_full_redraw = False
        elif selection_changed:
            # Only update the selection (much faster)
            self.context["drawing"]["begin_batch"]()
            self.update_selection_only(page_apps, start_index, current_layout)
            self.context["drawing"]["end_batch"]()
        
        # Update tracking variables
        self.last_page = self.current_page
        self.last_selection = self.selection
        self.last_layout = current_layout
    
    def calculate_layout(self, page_apps):
        """Calculate layout parameters"""
        # Get icon dimensions
        test_icon = page_apps[0].get("icon_normal") or page_apps[0].get("icon_selected")
        icon_w, icon_h = test_icon.size
        padding = 4
        
        # Calculate grid
        dots_width = 0
        available_width = 128 - dots_width
        max_cols = max(1, available_width // (icon_w + padding))
        page_app_count = len(page_apps)
        cols = min(page_app_count, max_cols)
        rows = (page_app_count + cols - 1) // cols

        total_grid_w = cols * (icon_w + padding) - padding
        total_grid_h = rows * (icon_h + padding) - padding

        x_offset = dots_width + (available_width - total_grid_w) // 2
        y_offset = (64 - total_grid_h) // 2
        
        return {
            'icon_w': icon_w, 'icon_h': icon_h, 'padding': padding,
            'cols': cols, 'rows': rows,
            'x_offset': x_offset, 'y_offset': y_offset,
            'page_app_count': page_app_count
        }
    
    def draw_all_page_apps(self, page_apps, start_index, layout):
        """Draw all apps for the current page"""
        for page_index, app in enumerate(page_apps):
            global_index = start_index + page_index
            col = page_index % layout['cols']
            row = page_index // layout['cols']

            x = layout['x_offset'] + col * (layout['icon_w'] + layout['padding'])
            y = layout['y_offset'] + row * (layout['icon_h'] + layout['padding'])

            self.draw_app(global_index, app, x, y, layout)
    
    def update_selection_only(self, page_apps, start_index, layout):
        """Efficiently update only the selection change"""
        # Find old and new selected app positions on current page
        old_page_index = self.last_selection - start_index if start_index <= self.last_selection < start_index + len(page_apps) else -1
        new_page_index = self.selection - start_index if start_index <= self.selection < start_index + len(page_apps) else -1
        
        # Clear and redraw old selection (if it was on this page)
        if 0 <= old_page_index < len(page_apps):
            app = page_apps[old_page_index]
            global_index = start_index + old_page_index
            col = old_page_index % layout['cols']
            row = old_page_index // layout['cols']
            x = layout['x_offset'] + col * (layout['icon_w'] + layout['padding'])
            y = layout['y_offset'] + row * (layout['icon_h'] + layout['padding'])
            
            # Clear the old icon area and redraw as unselected
            self.context["drawing"]["clear_area"](x, y, layout['icon_w'], layout['icon_h'])
            self.draw_app(global_index, app, x, y, layout)
        
        # Draw new selection (if it's on this page)
        if 0 <= new_page_index < len(page_apps):
            app = page_apps[new_page_index]
            global_index = start_index + new_page_index
            col = new_page_index % layout['cols']
            row = new_page_index // layout['cols']
            x = layout['x_offset'] + col * (layout['icon_w'] + layout['padding'])
            y = layout['y_offset'] + row * (layout['icon_h'] + layout['padding'])
            
            # Clear the area and redraw as selected
            self.context["drawing"]["clear_area"](x, y, layout['icon_w'], layout['icon_h'])
            self.draw_app(global_index, app, x, y, layout)
    
    def draw_pagination_dots(self):
        """Draw pagination dots on the left side using region-based drawing"""
        if self.total_pages <= 1:
            return
            
        # Calculate dot positioning
        dot_size_x = 1  # Slightly larger for better visibility
        dot_size_x_selected = 2  # Slightly larger for better visibility
        dot_size_y = 3  # Slightly larger for better visibility
        dot_spacing = 3
        total_dots_height = self.total_pages * dot_size_y + (self.total_pages - 1) * dot_spacing
        start_y = (64 - total_dots_height) // 2
        dot_x = 0
        
        # Track the entire dots region for clearing
        self.dots_region = (dot_x, start_y, dot_size_x_selected, total_dots_height)
        
        # Draw each dot
        for page in range(self.total_pages):
            y = start_y + page * (dot_size_y + dot_spacing)

            # Current page dot is filled, others are outlined
            if page == self.current_page:
                self.context["drawing"]["draw_area"](dot_x, y, dot_size_x_selected, dot_size_y, 255)
            else:
                self.context["drawing"]["draw_area"](dot_x, y, dot_size_x, dot_size_y, 255)

    def draw_app(self, index, app, x, y, layout):
        """Draw an app icon using region-based drawing"""
        # Store the region for this app
        self.app_regions[index] = (x, y, layout['icon_w'], layout['icon_h'])
        
        if index == self.selection:
            icon = app.get("icon_selected")
        else:
            icon = app.get("icon_normal")

        if icon:
            self.context["drawing"]["draw_image"](icon, x, y)


    def update(self):
        # Only redraw when necessary - the new system is much more efficient
        if self.needs_redraw:
            self.drawAllApps()
            self.needs_redraw = False
    
    def onkeyup(self, keycode):
        if keycode == "KEY_LEFT" or keycode == "KEY_A":
            old_selection = self.selection
            self.selection = (self.selection - 1) % self.app_count
            self.update_page_if_needed(old_selection)
            self.needs_redraw = True
        elif keycode == "KEY_RIGHT" or keycode == "KEY_D":
            old_selection = self.selection
            self.selection = (self.selection + 1) % self.app_count
            self.update_page_if_needed(old_selection)
            self.needs_redraw = True
        elif keycode == "KEY_UP" or keycode == "KEY_W":
            self.navigate_up()
        elif keycode == "KEY_DOWN" or keycode == "KEY_S":
            self.navigate_down()
        elif keycode == "KEY_ENTER" or keycode == "KEY_SPACE":
            if self.app_count > 0:
                selected_app = self.get_selected_app()
                if selected_app:
                    name = selected_app['name']
                    if self.user_prefs:
                        self.user_prefs.set_last_launched_app(name)
                        print(f"[Launcher] Saved last launched app: {name}")
                    
                    self.context["app_manager"].swap_app_async(
                        "launcher", name, update_rate_hz=20.0, delay=0.1
                    )
            else:
                print("[Launcher] No apps to launch")

    def navigate_up(self):
        """Navigate up in the grid layout"""
        if self.app_count == 0:
            return
            
        # Calculate current grid layout
        cols = self.get_current_page_cols()
        current_row = (self.selection % self.apps_per_page) // cols
        current_col = (self.selection % self.apps_per_page) % cols
        
        if current_row > 0:
            # Move up one row in the same page
            new_selection = self.selection - cols
            if new_selection >= self.current_page * self.apps_per_page:
                self.selection = new_selection
                self.needs_redraw = True
        else:
            # Move to previous page, bottom row
            if self.current_page > 0:
                self.current_page -= 1
                # Calculate position in previous page
                prev_page_apps = self.get_apps_on_page(self.current_page)
                prev_page_cols = self.get_current_page_cols()
                prev_page_rows = (prev_page_apps + prev_page_cols - 1) // prev_page_cols
                
                # Try to position in same column, bottom row
                target_row = prev_page_rows - 1
                target_selection = self.current_page * self.apps_per_page + target_row * prev_page_cols + current_col
                
                # Make sure we don't go beyond the available apps
                max_selection = self.current_page * self.apps_per_page + prev_page_apps - 1
                self.selection = min(target_selection, max_selection)
                self.needs_redraw = True
                self.needs_full_redraw = True  # Page change requires full redraw
    
    def navigate_down(self):
        """Navigate down in the grid layout"""
        if self.app_count == 0:
            return
            
        # Calculate current grid layout
        cols = self.get_current_page_cols()
        current_page_apps = self.get_apps_on_page(self.current_page)
        current_row = (self.selection % self.apps_per_page) // cols
        current_col = (self.selection % self.apps_per_page) % cols
        current_page_rows = (current_page_apps + cols - 1) // cols
        
        if current_row < current_page_rows - 1:
            # Move down one row in the same page
            new_selection = self.selection + cols
            max_selection = self.current_page * self.apps_per_page + current_page_apps - 1
            if new_selection <= max_selection:
                self.selection = new_selection
                self.needs_redraw = True
            else:
                # Try to position in the last row, same column if possible
                last_row_start = self.current_page * self.apps_per_page + (current_page_rows - 1) * cols
                target_selection = last_row_start + current_col
                if target_selection <= max_selection:
                    self.selection = target_selection
                    self.needs_redraw = True
                else:
                    # Go to the last available position
                    self.selection = max_selection
                    self.needs_redraw = True
        else:
            # Move to next page, top row
            if self.current_page < self.total_pages - 1:
                self.current_page += 1
                # Position in same column, top row
                target_selection = self.current_page * self.apps_per_page + current_col
                
                # Make sure we don't go beyond the available apps
                next_page_apps = self.get_apps_on_page(self.current_page)
                max_selection = self.current_page * self.apps_per_page + next_page_apps - 1
                self.selection = min(target_selection, max_selection)
                self.needs_redraw = True
                self.needs_full_redraw = True  # Page change requires full redraw
    
    def get_current_page_cols(self):
        """Get number of columns for current page layout"""
        page_apps = self.get_apps_on_page(self.current_page)
        if page_apps == 0:
            return 1
            
        # Get a reference app to determine icon size
        all_apps = self.get_valid_apps()
        if not all_apps:
            return 1
            
        start_index = self.current_page * self.apps_per_page
        test_app = all_apps[start_index]
        test_icon = test_app.get("icon_normal") or test_app.get("icon_selected")
        if not test_icon:
            return 1
            
        icon_w, icon_h = test_icon.size
        padding = 4
        dots_width = 0
        available_width = 128 - dots_width
        
        # Calculate maximum possible columns
        max_cols = max(1, available_width // (icon_w + padding))
        return min(page_apps, max_cols)

    def update_page_if_needed(self, old_selection):
        """Update current page if selection moved to a different page"""
        new_page = self.selection // self.apps_per_page
        if new_page != self.current_page:
            self.current_page = new_page
            self.needs_full_redraw = True  # Page change requires full redraw
    
    def get_apps_on_page(self, page):
        """Get number of apps on a specific page"""
        start_index = page * self.apps_per_page
        end_index = min(start_index + self.apps_per_page, self.app_count)
        return end_index - start_index
                
    def get_valid_apps(self):
        
        if self.valid_apps and len(self.valid_apps) > 0:
            return self.valid_apps
        
        valid_apps = []
        hidden_apps = []
        
        # Get hidden apps list from preferences
        if self.user_prefs:
            hidden_apps = self.user_prefs.get_hidden_apps()
        
        for app in self.context["apps"]["all"]:
            if app['metadata']['type'].lower() == "overlay":
                continue
            if app['name'].lower() == "launcher":
                continue
            
            # Skip hidden apps
            if app['name'] in hidden_apps:
                continue
                
            valid_apps.append(app)
        
        self.valid_apps = valid_apps
        return valid_apps
    
    def refresh_apps(self):
        """Refresh the apps list (clears cache to reload from preferences)"""
        self.valid_apps = []
        self.app_count = 0
        # Recalculate everything - force full redraw
        self.needs_redraw = True
        self.needs_full_redraw = True
        self.app_regions.clear()
        self.dots_region = None
                
    def get_selected_app(self):
        valid_apps = self.get_valid_apps()
        if 0 <= self.selection < len(valid_apps):
            return valid_apps[self.selection]
        return None

    def stop(self):
        print("[Launcher] Stopped")
