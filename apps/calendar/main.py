from interfaces import AppBase
import calendar
import datetime
import time
from PIL import Image, ImageDraw

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.display_queue = context["display_queue"]
        self.width = context["screen_width"]
        self.height = context["screen_height"]
        self.context = context
        
        # Current date
        self.current_date = datetime.date.today()
        self.selected_date = self.current_date
        
        # Navigation state
        self.view_month = self.current_date.month
        self.view_year = self.current_date.year
        
        # Display settings
        self.font_small = context["fonts"]["small"]
        self.font_default = context["fonts"]["default"]
        self.font_bold = context["fonts"]["bold"]
        
        # Calendar layout
        self.header_height = 8
        self.day_names_height = 8
        self.cell_width = 18
        self.cell_height = 8
        self.start_x = 2
        self.start_y = self.header_height + self.day_names_height + 2
        
        # Month names
        self.month_names = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        
        # Day names (abbreviated)
        self.day_names = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
        
    def start(self):
        self.draw_calendar()
        
    def update(self):
        # No continuous updates needed for calendar
        pass
    
    def draw_calendar(self):
        """Draw the complete calendar view"""
        # Clear the screen
        self.display_queue.put(("clear_base",))
        
        # Draw month/year header
        self.draw_header()
        
        # Draw day names
        self.draw_day_names()
        
        # Draw calendar grid
        self.draw_calendar_grid()
        
    def draw_header(self):
        """Draw the month/year header"""
        month_name = self.month_names[self.view_month - 1]
        header_text = f"{month_name} {self.view_year}"
        
        # Center the header
        font_width, font_height = self.context["get_text_size"](header_text, self.font_small)
        header_x = (self.width - font_width) // 2
        
        self.display_queue.put(("draw_base_text", self.font_small, header_text, header_x, 2))
        
    def draw_day_names(self):
        """Draw the day names row"""
        y_pos = self.header_height + 2
        
        for i, day_name in enumerate(self.day_names):
            x_pos = self.start_x + (i * self.cell_width)
            self.display_queue.put(("draw_base_text", self.font_small, day_name, x_pos, y_pos))
            
    def draw_calendar_grid(self):
        """Draw the calendar grid with dates"""
        # Get calendar data for the current month
        cal = calendar.monthcalendar(self.view_year, self.view_month)
        
        for week_num, week in enumerate(cal):
            for day_num, day in enumerate(week):
                if day == 0:  # Empty cell
                    continue
                    
                x_pos = self.start_x + (day_num * self.cell_width)
                y_pos = self.start_y + (week_num * self.cell_height)
                
                # Check if this is today
                is_today = (day == self.current_date.day and 
                           self.view_month == self.current_date.month and 
                           self.view_year == self.current_date.year)
                
                # Check if this is the selected date
                is_selected = (day == self.selected_date.day and 
                              self.view_month == self.selected_date.month and 
                              self.view_year == self.selected_date.year)
                
                # Choose font and draw background if needed
                if is_today:
                    # Draw background rectangle for today
                    self.draw_cell_outline(x_pos - 1, y_pos - 1, self.cell_width - 2, self.cell_height - 1)
                    font_to_use = self.font_small
                elif is_selected:
                    # Draw outline for selected date
                    self.draw_cell_outline_dashed(x_pos - 1, y_pos - 1, self.cell_width - 2, self.cell_height - 1)
                    font_to_use = self.font_small
                else:
                    font_to_use = self.font_small
                
                # Draw the day number
                day_str = str(day)
                self.display_queue.put(("draw_base_text", font_to_use, day_str, x_pos, y_pos))
                
    def draw_cell_outline_dashed(self, x, y, width, height):
        """Draw a dashed outline around a cell"""
        from PIL import Image, ImageDraw
        
        # Create a small image for the outline
        outline_width = int(width) + 2
        outline_height = int(height) + 2
        outline_img = Image.new("1", (outline_width, outline_height), 0)  # Black background
        draw = ImageDraw.Draw(outline_img)
        
        # Draw dashed outline manually
        dash_length = 3
        gap_length = 2
        
        # Top edge
        for i in range(0, outline_width, dash_length + gap_length):
            end_x = min(i + dash_length - 1, outline_width - 1)
            if i < outline_width:
                draw.line([i, 0, end_x, 0], fill=1)
        
        # Bottom edge
        for i in range(0, outline_width, dash_length + gap_length):
            end_x = min(i + dash_length - 1, outline_width - 1)
            if i < outline_width:
                draw.line([i, outline_height - 1, end_x, outline_height - 1], fill=1)
        
        # Left edge
        for i in range(0, outline_height, dash_length + gap_length):
            end_y = min(i + dash_length - 1, outline_height - 1)
            if i < outline_height:
                draw.line([0, i, 0, end_y], fill=1)
        
        # Right edge
        for i in range(0, outline_height, dash_length + gap_length):
            end_y = min(i + dash_length - 1, outline_height - 1)
            if i < outline_height:
                draw.line([outline_width - 1, i, outline_width - 1, end_y], fill=1)
        
        # Draw the outline image to the display
        self.display_queue.put(("draw_base_image", outline_img, int(x), int(y)))
        
    def draw_cell_outline(self, x, y, width, height):
        """Draw an outline around a cell"""
        
        # Create a small image for the outline
        outline_width = int(width) + 2
        outline_height = int(height) + 2
        outline_img = Image.new("1", (outline_width, outline_height), 0)  # Black background
        draw = ImageDraw.Draw(outline_img)
        
        # Draw the outline rectangle
        draw.rectangle([0, 0, outline_width-1, outline_height-1], outline=1, fill=0)
        
        # Draw the outline image to the display
        self.display_queue.put(("draw_base_image", outline_img, int(x), int(y)))
        
    def navigate_month(self, direction):
        """Navigate to previous (-1) or next (1) month"""
        if direction == -1:  # Previous month
            if self.view_month == 1:
                self.view_month = 12
                self.view_year -= 1
            else:
                self.view_month -= 1
        elif direction == 1:  # Next month
            if self.view_month == 12:
                self.view_month = 1
                self.view_year += 1
            else:
                self.view_month += 1
                
        # Update selected date if it's not valid in the new month
        try:
            self.selected_date = datetime.date(self.view_year, self.view_month, self.selected_date.day)
        except ValueError:
            # Day doesn't exist in new month (e.g., Jan 31 -> Feb)
            last_day = calendar.monthrange(self.view_year, self.view_month)[1]
            self.selected_date = datetime.date(self.view_year, self.view_month, last_day)
            
        self.draw_calendar()
        
    def navigate_day(self, direction):
        """Navigate to previous (-1) or next (1) day"""
        delta = datetime.timedelta(days=direction)
        new_date = self.selected_date + delta
        
        # Update view month/year if we moved to a different month
        if new_date.month != self.view_month or new_date.year != self.view_year:
            self.view_month = new_date.month
            self.view_year = new_date.year
            
        self.selected_date = new_date
        self.draw_calendar()
        
    def go_to_today(self):
        """Go back to today's date"""
        self.current_date = datetime.date.today()
        self.selected_date = self.current_date
        self.view_month = self.current_date.month
        self.view_year = self.current_date.year
        self.draw_calendar()
        
    def get_date_info(self):
        """Get information about the selected date"""
        weekday = self.selected_date.strftime("%A")
        date_str = self.selected_date.strftime("%B %d, %Y")
        return f"{weekday}, {date_str}"
        
    def onkeydown(self, keycode):
        """Handle key press events"""
        pass
        
    def onkeyup(self, keycode):
        """Handle key release events"""
        # Navigation keys
        if keycode == "KEY_LEFT":
            self.navigate_day(-1)
        elif keycode == "KEY_RIGHT":
            self.navigate_day(1)
        elif keycode == "KEY_UP":
            self.navigate_day(-7)  # Previous week
        elif keycode == "KEY_DOWN":
            self.navigate_day(7)   # Next week
            
        # Special functions
        elif keycode == "KEY_HOME" or keycode == "KEY_H":
            self.go_to_today()
        elif keycode == "KEY_ENTER":
            # Speak the selected date
            date_info = self.get_date_info()
            print(f"Selected date: {date_info}")
            
        # App control
        elif keycode == "KEY_R":
            if "app_manager" in self.context:
                self.context["app_manager"].reload_app("calendar")
        # switch to the launcher if 'Esc' is pressed
        elif keycode == "KEY_ESC":
            self.display_queue.put(("set_screen", "Launcher", "Switching to Launcher..."))
            self.context["app_manager"].swap_app_async("clock", "launcher", update_rate_hz=20.0, delay=0.1)
