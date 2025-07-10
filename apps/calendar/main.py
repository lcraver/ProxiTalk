from interfaces import AppBase
import calendar
import datetime
import time
import json
import os
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
        
        # Load events from JSON file
        self.events = self.load_events()
        
    def load_events(self):
        """Load events from the events.json file"""
        try:
            events_file = os.path.join(os.path.dirname(__file__), "events.json")
            with open(events_file, 'r') as f:
                data = json.load(f)
                return data.get("events", [])
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error loading events: {e}")
            return []
            
    def get_events_for_date(self, date):
        """Get all events for a specific date"""
        date_str = date.strftime("%Y-%m-%d")
        return [event for event in self.events if event["date"] == date_str]
        
    def has_events(self, date):
        """Check if a date has any events"""
        return len(self.get_events_for_date(date)) > 0
        
    def start(self):
        # Ensure events are loaded
        self.events = self.load_events()
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
                
                # Create date object for this day
                current_cell_date = datetime.date(self.view_year, self.view_month, day)
                
                # Check if this is today
                is_today = (day == self.current_date.day and 
                           self.view_month == self.current_date.month and 
                           self.view_year == self.current_date.year)
                
                # Check if this is the selected date
                is_selected = (day == self.selected_date.day and 
                              self.view_month == self.selected_date.month and 
                              self.view_year == self.selected_date.year)
                
                # Check if this date has events
                has_events = self.has_events(current_cell_date)
                
                # Choose font and draw background if needed
                if is_today:
                    # Draw background rectangle for today
                    self.draw_cell_outline(x_pos - 2, y_pos - 1, self.cell_width - 1, self.cell_height - 1)
                    font_to_use = self.font_small
                elif is_selected:
                    # Draw outline for selected date
                    self.draw_cell_outline_dashed(x_pos - 2, y_pos - 1, self.cell_width - 1, self.cell_height - 1)
                    font_to_use = self.font_small
                else:
                    font_to_use = self.font_small
                
                # Draw the day number
                day_str = str(day)
                self.display_queue.put(("draw_base_text", font_to_use, day_str, x_pos, y_pos))
                
                # Draw event indicator if there are events
                if has_events:
                    self.draw_event_indicator(x_pos + self.cell_width - 6, y_pos + 1)
                
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
        
    def draw_event_indicator(self, x, y):
        """Draw a small dot to indicate events on a date"""
        # Create a small 3x3 image for the event indicator
        indicator_img = Image.new("1", (3, 3), 0)  # Black background
        draw = ImageDraw.Draw(indicator_img)
        
        # Draw a small filled circle/dot
        draw.ellipse([0, 0, 2, 2], fill=1)
        
        # Draw the indicator to the display
        self.display_queue.put(("draw_base_image", indicator_img, int(x), int(y)))
        
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
        
        # Get events for this date
        events = self.get_events_for_date(self.selected_date)
        
        info = f"{weekday}, {date_str}"
        if events:
            info += f" - {len(events)} event(s):"
            for event in events:
                info += f"\n  • {event['time']} - {event['title']}"
                if event.get('description'):
                    info += f" ({event['description']})"
        else:
            info += " - No events"
            
        return info
        
    def get_date_info_for_tts(self):
        """Get date information formatted for TTS (more natural speech)"""
        weekday = self.selected_date.strftime("%A")
        date_str = self.selected_date.strftime("%B %d")
        
        # Get events for this date
        events = self.get_events_for_date(self.selected_date)
        
        if events:
            if len(events) == 1:
                info = f"It is {weekday} {date_str} and you have 1 event"
            else:
                info = f"It is {weekday} {date_str} and you have {len(events)} events"
            
            for i, event in enumerate(events):
                # Convert 24-hour time to 12-hour format for TTS
                try:
                    time_obj = datetime.datetime.strptime(event['time'], "%H:%M")
                    time_str = time_obj.strftime("%I:%M %p").lstrip('0')
                except:
                    time_str = event['time']
                
                info += f" At {time_str} you have {event['title']}"
                if event.get('description'):
                    info += f" which is {event['description']}"
                
                # Add natural connectors between events
                if i < len(events) - 1:
                    info += " also"
        else:
            info = f"It is {weekday} {date_str} and you have no events scheduled"
            
        return info
        
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
            # Use TTS to speak the selected date and events
            date_info = self.get_date_info()
            print(f"Selected date: {date_info}")
            
            # Use TTS-friendly format for better speech
            if "run_tts" in self.context:
                tts_info = self.get_date_info_for_tts()
                print(f"TTS info: {tts_info}")
                self.context["run_tts"](tts_info, background=True)
        elif keycode == "KEY_E":
            # Show events for selected date and use TTS
            events = self.get_events_for_selected_date()
            if events:
                # Print detailed events to console
                print(f"Events for {self.selected_date.strftime('%A, %B %d, %Y')}:")
                for event in events:
                    print(f"  • {event['time']} - {event['title']}")
                    if event.get('description'):
                        print(f"    {event['description']}")
                
                # Create TTS-friendly text for events only
                if len(events) == 1:
                    events_text = f"You have 1 event"
                else:
                    events_text = f"You have {len(events)} events"
                
                for i, event in enumerate(events):
                    # Convert 24-hour time to 12-hour format for TTS
                    try:
                        time_obj = datetime.datetime.strptime(event['time'], "%H:%M")
                        time_str = time_obj.strftime("%I:%M %p").lstrip('0')
                    except:
                        time_str = event['time']
                    
                    events_text += f" at {time_str} you have {event['title']}"
                    if event.get('description'):
                        events_text += f" {event['description']}"
                    
                    # Add natural pauses between events
                    if i < len(events) - 1:
                        events_text += " also"
                        
                print(f"Events TTS: {events_text}")
                
                # Use TTS to speak the events
                if "run_tts" in self.context:
                    self.context["run_tts"](events_text, background=True)
            else:
                no_events_text = f"No events scheduled for {self.selected_date.strftime('%A %B %d')}"
                print(no_events_text)
                if "run_tts" in self.context:
                    self.context["run_tts"](no_events_text, background=True)
        elif keycode == "KEY_F5":
            # Reload events from file
            self.reload_events()
            print("Events reloaded from file")
            
        # App control
        elif keycode == "KEY_R":
            if "app_manager" in self.context:
                self.context["app_manager"].reload_app("calendar")
        # switch to the launcher if 'Esc' is pressed
        elif keycode == "KEY_ESC":
            self.set_screen("Launcher", "Switching to Launcher...")
            self.context["app_manager"].swap_app_async("clock", "launcher", update_rate_hz=20.0, delay=0.1)
            
    def save_events(self):
        """Save events back to the JSON file"""
        try:
            events_file = os.path.join(os.path.dirname(__file__), "events.json")
            data = {"events": self.events}
            with open(events_file, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving events: {e}")
            return False
            
    def add_event(self, title, date, time="00:00", description=""):
        """Add a new event"""
        # Find the next available ID
        existing_ids = [int(event.get("id", 0)) for event in self.events]
        next_id = str(max(existing_ids) + 1 if existing_ids else 1)
        
        new_event = {
            "id": next_id,
            "title": title,
            "date": date.strftime("%Y-%m-%d") if isinstance(date, datetime.date) else date,
            "time": time,
            "description": description,
        }
        
        self.events.append(new_event)
        self.save_events()
        self.draw_calendar()  # Refresh the display
        return new_event
        
    def remove_event(self, event_id):
        """Remove an event by ID"""
        self.events = [event for event in self.events if event.get("id") != event_id]
        self.save_events()
        self.draw_calendar()  # Refresh the display
        
    def get_events_for_selected_date(self):
        """Get events for the currently selected date"""
        return self.get_events_for_date(self.selected_date)
        
    def reload_events(self):
        """Reload events from the JSON file"""
        self.events = self.load_events()
        self.draw_calendar()  # Refresh the display
