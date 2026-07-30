from interfaces import AppBase
from PIL import Image, ImageDraw
import os

ROOT_VIEW_KEY = "__root__"

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.selection = 0
        self.app_count = 0
        self.user_prefs = context.get("user_preferences")
        self.view_cache = {}
        self.structure_dirty = True
        self.current_folder = None
        self.navigation_stack = []
        self.back_icon_normal = None
        self.back_icon_selected = None
        
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
        self.refresh_apps()
        
        # Load last selection from preferences if available
        if self.user_prefs:
            last_app_name = self.user_prefs.get_last_launched_app()
            if last_app_name:
                self.focus_on_app(last_app_name)
        
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
    
    def onkeydown(self, keycode):
        if keycode == "KEY_LEFT" or keycode == "KEY_A":
            if self.app_count == 0:
                return
            old_selection = self.selection
            self.selection = (self.selection - 1) % self.app_count
            self.update_page_if_needed(old_selection)
            self.needs_redraw = True
        elif keycode == "KEY_RIGHT" or keycode == "KEY_D":
            if self.app_count == 0:
                return
            old_selection = self.selection
            self.selection = (self.selection + 1) % self.app_count
            self.update_page_if_needed(old_selection)
            self.needs_redraw = True
        elif keycode == "KEY_UP" or keycode == "KEY_W":
            self.navigate_up()
        elif keycode == "KEY_DOWN" or keycode == "KEY_S":
            self.navigate_down()
        elif keycode == "KEY_ENTER" or keycode == "KEY_SPACE":
            selected_entry = self.get_selected_entry()
            if not selected_entry:
                print("[Launcher] No selection available")
                return

            entry_type = selected_entry.get('entry_type', 'app')
            if entry_type == 'folder':
                self.enter_folder(selected_entry.get('name'))
            elif entry_type == 'back':
                self.exit_folder()
            elif entry_type == 'app':
                name = selected_entry['name']
                if self.user_prefs:
                    self.user_prefs.set_last_launched_app(name)
                    print(f"[Launcher] Saved last launched app: {name}")
                self.context["app_manager"].swap_app_async(
                    "launcher", name, update_rate_hz=20.0, delay=0.1
                )
            else:
                print(f"[Launcher] Unknown entry type: {entry_type}")
        elif keycode == "KEY_BACKSPACE" or keycode == "KEY_ESC":
            if self.handle_back_navigation():
                self.needs_redraw = True

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
        self.ensure_view_cache()
        view_key = self.get_current_view_key()
        entries = self.view_cache.get(view_key, [])
        self.app_count = len(entries)
        if self.app_count == 0:
            self.selection = 0
        elif self.selection >= self.app_count:
            self.selection = self.app_count - 1
        return entries
    
    def refresh_apps(self):
        """Refresh cached app structures and request a redraw."""
        self.view_cache = {}
        self.structure_dirty = True
        self.app_count = 0
        self.needs_redraw = True
        self.needs_full_redraw = True
        self.app_regions.clear()
        self.dots_region = None
    
    def get_selected_entry(self):
        entries = self.get_valid_apps()
        if 0 <= self.selection < len(entries):
            return entries[self.selection]
        return None

    def focus_on_app(self, app_name):
        if not app_name:
            return
        self.ensure_view_cache()
        root_entries = self.view_cache.get(ROOT_VIEW_KEY, [])
        for i, entry in enumerate(root_entries):
            if entry.get("entry_type") == "app" and entry.get("name") == app_name:
                self.current_folder = None
                self.selection = i
                self.current_page = i // self.apps_per_page
                print(f"[Launcher] Auto-selected last app: {app_name} (index {i}, page {self.current_page})")
                return
        for folder_name, entries in self.view_cache.items():
            if folder_name == ROOT_VIEW_KEY:
                continue
            for i, entry in enumerate(entries):
                if entry.get("entry_type") == "app" and entry.get("name") == app_name:
                    self.current_folder = folder_name
                    self.selection = i
                    self.current_page = i // self.apps_per_page
                    self.navigation_stack = []
                    print(f"[Launcher] Auto-selected last app inside '{folder_name}': {app_name} (index {i}, page {self.current_page})")
                    return

    def enter_folder(self, folder_name):
        self.ensure_view_cache()
        if folder_name not in self.view_cache:
            print(f"[Launcher] Folder '{folder_name}' not found")
            return
        self.navigation_stack.append({
            "folder": self.current_folder,
            "selection": self.selection,
            "page": self.current_page,
        })
        self.current_folder = folder_name
        self.selection = 1 if len(self.view_cache[folder_name]) > 1 else 0
        self.current_page = 0
        self.last_page = -1
        self.last_selection = -1
        self.needs_full_redraw = True
        self.needs_redraw = True

    def exit_folder(self):
        if not self.navigation_stack:
            self.current_folder = None
            self.selection = 0
            self.current_page = 0
        else:
            state = self.navigation_stack.pop()
            self.current_folder = state.get("folder")
            self.selection = state.get("selection", 0)
            self.current_page = state.get("page", 0)
        self.last_page = -1
        self.last_selection = -1
        self.needs_full_redraw = True
        self.needs_redraw = True

    def handle_back_navigation(self):
        if not self.current_folder:
            return False
        self.exit_folder()
        return True

    def ensure_view_cache(self):
        if not self.structure_dirty and self.view_cache:
            return
        self.build_view_cache()

    def build_view_cache(self):
        self.view_cache = {}
        hidden_apps = set(self.user_prefs.get_hidden_apps()) if self.user_prefs else set()
        root_apps = []
        folder_children = {}
        for app in self.context["apps"]["all"]:
            metadata_type = app['metadata'].get('type', 'app').lower()
            if metadata_type == "overlay":
                continue
            if app['name'].lower() == "launcher":
                continue
            if app['name'] in hidden_apps:
                continue

            entry = dict(app)
            entry['entry_type'] = "app"
            entry['display_name'] = app['metadata'].get('name', app['name'])

            relative_path = app.get("path") or app['name']
            segments = self.split_relative_path(relative_path)
            if len(segments) <= 1:
                root_apps.append(entry)
                continue

            folder_name = segments[0]
            entry['folder'] = folder_name
            folder_children.setdefault(folder_name, []).append(entry)

        # Sort entries for consistent layout
        root_apps.sort(key=lambda item: item.get('display_name', item.get('name', '')).lower())
        folder_names = sorted(folder_children.keys(), key=lambda name: name.lower())

        root_entries = []
        for folder_name in folder_names:
            children = folder_children[folder_name]
            children.sort(key=lambda item: item.get('display_name', item.get('name', '')).lower())
            folder_entry = {
                'entry_type': 'folder',
                'name': folder_name,
                'display_name': self.format_folder_name(folder_name),
                'icon_normal': self.load_icon_asset(folder_name),
                'icon_selected': self.load_icon_asset(folder_name, selected=True),
            }
            if not folder_entry['icon_normal']:
                folder_entry['icon_normal'] = self.get_back_icon(False)
            if not folder_entry['icon_selected']:
                folder_entry['icon_selected'] = folder_entry['icon_normal'] or self.get_back_icon(True)

            folder_view = [self.create_back_entry(folder_name)] + children
            self.view_cache[folder_name] = folder_view
            root_entries.append(folder_entry)

        root_entries.extend(root_apps)
        self.view_cache[ROOT_VIEW_KEY] = root_entries
        self.structure_dirty = False

        # Validate current navigation state
        if self.current_folder and self.current_folder not in self.view_cache:
            self.current_folder = None
            self.navigation_stack = []

        # Drop history entries for removed folders
        if self.navigation_stack:
            self.navigation_stack = [
                state for state in self.navigation_stack
                if not state.get("folder") or state.get("folder") in self.view_cache
            ]

    def split_relative_path(self, relative_path):
        normalized = (relative_path or "").replace("\\", "/")
        parts = [segment for segment in normalized.split("/") if segment]
        return parts or [relative_path]

    def format_folder_name(self, folder_name):
        cleaned = folder_name.lstrip("_")
        if not cleaned:
            cleaned = folder_name
        cleaned = cleaned.replace("_", " ").replace("-", " ")
        return cleaned.title()

    def create_back_entry(self, folder_name):
        return {
            'entry_type': 'back',
            'name': '__back__',
            'folder': folder_name,
            'display_name': 'Back',
            'icon_normal': self.get_back_icon(False),
            'icon_selected': self.get_back_icon(True),
        }

    def get_back_icon(self, selected=False):
        if self.back_icon_normal is None or self.back_icon_selected is None:
            self.load_back_icons()
        return self.back_icon_selected if selected else self.back_icon_normal

    def load_back_icons(self):
        icon_dir = self.context.get("app_path") or os.path.join(
            self.context.get("APPS_DIR", ""), "launcher"
        )
        normal_path = os.path.join(icon_dir, "back.png")
        selected_path = os.path.join(icon_dir, "selected_back.png")

        def load_icon(path):
            if not path or not os.path.isfile(path):
                return None
            try:
                return Image.open(path).convert("1")
            except Exception as exc:
                print(f"[Launcher] Failed to load back icon '{path}': {exc}")
                return None

        normal_icon = load_icon(normal_path)
        selected_icon = load_icon(selected_path)

        if normal_icon is None and selected_icon is None:
            print("[Launcher] Back icon assets missing, generating fallback icons")
            normal_icon, selected_icon = self.generate_back_icons()
        else:
            if normal_icon is None:
                normal_icon = selected_icon
            if selected_icon is None:
                selected_icon = normal_icon

        self.back_icon_normal = normal_icon
        self.back_icon_selected = selected_icon

    def generate_back_icons(self):
        size = (32, 32)
        normal = Image.new("1", size, 0)
        draw = ImageDraw.Draw(normal)
        arrow = [(22, 8), (14, 8), (8, 16), (14, 24), (22, 24), (16, 16)]
        draw.polygon(arrow, fill=255)
        draw.rectangle([16, 12, 24, 20], fill=0)

        selected = Image.new("1", size, 0)
        draw_selected = ImageDraw.Draw(selected)
        draw_selected.rectangle([0, 0, 31, 31], fill=255)
        draw_selected.rectangle([2, 2, 29, 29], fill=0)
        draw_selected.polygon(arrow, fill=255)
        draw_selected.rectangle([16, 12, 24, 20], fill=0)

        return normal, selected

    def load_icon_asset(self, target_name, selected=False):
        loader = self.context.get("load_icon")
        if not loader:
            return None
        try:
            icon = loader(target_name, "selected" if selected else None)
        except Exception as exc:
            print(f"[Launcher] Failed to load icon for {target_name}: {exc}")
            icon = None
        if icon or not selected:
            return icon

        # Fallback for folders that use selected_icon.png naming
        apps_dir = self.context.get("APPS_DIR")
        if not apps_dir:
            return None
        relative = target_name.replace("/", os.sep).replace("\\", os.sep)
        alt_path = os.path.join(apps_dir, relative, "selected_icon.png")
        if os.path.isfile(alt_path):
            try:
                return Image.open(alt_path).convert("1")
            except Exception as exc:
                print(f"[Launcher] Failed fallback icon load for {target_name}: {exc}")
        return None

    def get_current_view_key(self):
        return self.current_folder or ROOT_VIEW_KEY

    def stop(self):
        print("[Launcher] Stopped")
