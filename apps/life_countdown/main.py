from interfaces import AppBase
import time
import threading
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.display_queue = context["display_queue"]
        self.width = context["screen_width"]
        self.height = context["screen_height"]
        self.font = context["fonts"]["small"]
        
        # User configuration - these could be moved to a config file
        self.user_age = 29  # Current age in years
        self.user_country = "USA"  # Country code
        self.user_gender = "F"  # M for Male, F for Female
        self.user_birth_date = datetime(1995, 10, 10)  # Birth date for precise calculation
        
        # Life expectancy data by country and gender (2023 estimates)
        self.life_expectancy_data = {
            "USA": {"M": 76.4, "F": 81.4},
            "Canada": {"M": 79.8, "F": 84.1},
            "UK": {"M": 79.4, "F": 83.1},
            "Germany": {"M": 78.6, "F": 83.4},
            "France": {"M": 79.3, "F": 85.3},
            "Japan": {"M": 81.5, "F": 87.6},
            "Australia": {"M": 81.2, "F": 85.4},
            "Brazil": {"M": 73.1, "F": 80.2},
            "China": {"M": 75.0, "F": 79.9},
            "India": {"M": 68.4, "F": 71.0},
            "Russia": {"M": 68.2, "F": 78.5},
            "Mexico": {"M": 72.9, "F": 78.1},
            "South Africa": {"M": 62.3, "F": 68.5},
            "Nigeria": {"M": 53.4, "F": 55.7},
            "World": {"M": 70.8, "F": 76.0}  # Global average
        }
        
        # Display settings
        self.display_active = False  # Only show when triggered
        self.update_interval = 1.0  # Update every second
        self.last_update_time = 0
        
        # Timer for clearing display
        self.clear_timer_thread = None
        self.clear_timer_lock = threading.Lock()
        self.clear_timer_stop_flag = threading.Event()
        
        # Display position
        self.display_y = 1  # Top of screen
        self.last_drawn_area = None
        
    def start(self):
        """Initialize the life countdown display"""
        print("[Life Countdown] Started")
        self.display_active = False  # Don't show on startup
        self.last_update_time = 0
    
    def calculate_remaining_seconds(self):
        """Calculate remaining seconds to live based on life expectancy"""
        # Get life expectancy for user's country and gender
        country_data = self.life_expectancy_data.get(self.user_country, self.life_expectancy_data["World"])
        life_expectancy_years = country_data.get(self.user_gender, country_data["M"])
        
        # Calculate expected death date
        expected_death_date = self.user_birth_date + timedelta(days=life_expectancy_years * 365.25)
        
        # Calculate remaining time
        now = datetime.now()
        remaining_time = expected_death_date - now
        
        # Convert to seconds
        remaining_seconds = int(remaining_time.total_seconds())
        
        # Ensure we don't show negative numbers
        return max(0, remaining_seconds)
    
    def format_time_display(self, total_seconds):
        """Format seconds into a readable time display"""
        if total_seconds <= 0:
            return "Time's up!"
        
        # Calculate years, days, hours, minutes, seconds
        years = total_seconds // (365.25 * 24 * 3600)
        remaining = total_seconds % (365.25 * 24 * 3600)
        days = int(remaining // (24 * 3600))
        remaining = remaining % (24 * 3600)
        hours = int(remaining // 3600)
        remaining = remaining % 3600
        minutes = int(remaining // 60)
        seconds = int(remaining % 60)
        
        # Format based on magnitude
        if years > 0:
            return f"{int(years)}y {days}d {hours}h {minutes}m {seconds}s"
        elif days > 0:
            return f"{days}d {hours}h {minutes}m {seconds}s"
        elif hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        else:
            return f"{minutes}m {seconds}s"
    
    def show_countdown_feedback(self):
        """Show the countdown for a brief period"""
        try:
            # Calculate remaining time
            remaining_seconds = self.calculate_remaining_seconds()
            
            # Create display text - use shorter format for screen space
            countdown_text = f"{remaining_seconds:,} secs left"  # Show raw seconds count
            
            # Get text dimensions
            text_width, text_height = self.context["get_text_size"](countdown_text, self.font)
            text_width += 1   # Add padding
            text_height += 2  # Add padding
            
            # Calculate centered position
            center_x = (self.width - text_width) // 2
            
            # Create text image with white background and black text (inverted)
            img = Image.new("1", (text_width, text_height), 1)  # White background
            draw = ImageDraw.Draw(img)
            draw.text((1, 0), countdown_text, font=self.font, fill=0)  # Black text
            
            # Clear any existing display
            if self.last_drawn_area:
                x, y, w, h = self.last_drawn_area
                self.display_queue.put(("clear_overlay_area", x, y, w, h))
            
            # Display the countdown
            self.display_queue.put(("draw_overlay_image", img, center_x, self.display_y))
            
            # Remember the drawn area
            self.last_drawn_area = (center_x, self.display_y, text_width, text_height)
            
            # Start timer to clear after delay
            self._start_clear_timer(center_x, self.display_y, text_width, text_height)
            
            print(f"[Life Countdown] Showed '{countdown_text}' at ({center_x}, {self.display_y})")
            
        except Exception as e:
            print(f"[Life Countdown] Error showing countdown: {e}")
            import traceback
            traceback.print_exc()
    
    def _start_clear_timer(self, x, y, width, height, delay=2.0):
        """Start a timer to clear the display after a delay"""
        with self.clear_timer_lock:
            # Signal any running thread to stop
            self.clear_timer_stop_flag.set()
            if self.clear_timer_thread and self.clear_timer_thread.is_alive():
                self.clear_timer_thread.join()

            self.clear_timer_stop_flag = threading.Event()

            def clear_later():
                if not self.clear_timer_stop_flag.wait(delay):
                    self.display_queue.put(("clear_overlay_area", x, y, width, height))
                    self.last_drawn_area = None

            self.clear_timer_thread = threading.Thread(target=clear_later, daemon=True)
            self.clear_timer_thread.start()
    
    def update(self):
        """Called by the main app loop - no continuous updates needed"""
        pass
    
    def onkeyup(self, keycode):
        """Handle key inputs for configuration"""
        # Show countdown with L key
        if keycode == "KEY_L":  # L key to show life countdown
            self.show_countdown_feedback()
        elif keycode == "KEY_C":  # C key to configure
            self.cycle_country()
            self.show_countdown_feedback()  # Show updated countdown
        elif keycode == "KEY_G":  # G key to toggle gender
            self.toggle_gender()
            self.show_countdown_feedback()  # Show updated countdown
        elif keycode == "KEY_MINUS":  # Minus key to decrease age
            self.adjust_age(-1)
            self.show_countdown_feedback()  # Show updated countdown
        elif keycode == "KEY_EQUAL":  # Plus/Equal key to increase age
            self.adjust_age(1)
            self.show_countdown_feedback()  # Show updated countdown
    
    def toggle_display(self):
        """Toggle the countdown display on/off"""
        self.display_active = not self.display_active
        if not self.display_active and self.last_drawn_area:
            # Clear the display
            x, y, w, h = self.last_drawn_area
            self.display_queue.put(("clear_overlay_area", x, y, w, h))
            self.last_drawn_area = None
        print(f"[Life Countdown] Display {'enabled' if self.display_active else 'disabled'}")
    
    def cycle_country(self):
        """Cycle through available countries"""
        countries = list(self.life_expectancy_data.keys())
        current_index = countries.index(self.user_country)
        next_index = (current_index + 1) % len(countries)
        self.user_country = countries[next_index]
        print(f"[Life Countdown] Country changed to: {self.user_country}")
    
    def toggle_gender(self):
        """Toggle between Male and Female"""
        self.user_gender = "F" if self.user_gender == "M" else "M"
        gender_name = "Female" if self.user_gender == "F" else "Male"
        print(f"[Life Countdown] Gender changed to: {gender_name}")
    
    def adjust_age(self, delta):
        """Adjust the user's age"""
        self.user_age = max(0, min(120, self.user_age + delta))
        # Update birth date based on new age
        current_year = datetime.now().year
        birth_year = current_year - self.user_age
        self.user_birth_date = datetime(birth_year, self.user_birth_date.month, self.user_birth_date.day)
        print(f"[Life Countdown] Age adjusted to: {self.user_age}")
    
    def get_status_info(self):
        """Get current configuration for display"""
        country_data = self.life_expectancy_data.get(self.user_country, self.life_expectancy_data["World"])
        life_expectancy = country_data.get(self.user_gender, country_data["M"])
        gender_name = "Female" if self.user_gender == "F" else "Male"
        
        return {
            "age": self.user_age,
            "country": self.user_country,
            "gender": gender_name,
            "life_expectancy": life_expectancy,
            "display_active": self.display_active
        }
    
    def stop(self):
        """Clean up when app stops"""
        print("[Life Countdown] Stopping...")
        self.display_active = False
        
        # Stop any running timer
        self.clear_timer_stop_flag.set()
        
        # Clear any displayed countdown
        if self.last_drawn_area:
            x, y, w, h = self.last_drawn_area
            self.display_queue.put(("clear_overlay_area", x, y, w, h))
        
        print("[Life Countdown] Stopped")
