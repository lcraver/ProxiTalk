from interfaces import AppBase
import random
import time

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.play_sfx = context["audio"]["play_sfx"]
        self.run_tts = context["tts"]["run"]
        self.path = context["app_path"]
        
        # Game constants
        self.GRID_WIDTH = 32
        self.GRID_HEIGHT = 16
        self.CELL_SIZE = 4  # 4x4 pixels per cell (128/32 = 4, 64/16 = 4)
        
        # Game states
        self.PLAYING = 0
        self.GAME_OVER = 1
        self.PAUSED = 2
        
        # Game state
        self.reset_game()
        
        # Timing
        self.move_timer = 0
        self.move_interval = 8  # Move every 10 ticks (0.5 seconds at 20Hz)
        
        # Performance optimization - track what needs updating
        self.needs_full_redraw = True
        self.needs_score_update = False
        self.old_tail_position = None  # Track where the tail was for clearing
        self.old_food_position = None  # Track where food was for clearing
        self.old_score = 0
        
    def reset_game(self):
        """Reset the game to initial state"""
        # hebi starts in the middle, moving right
        self.hebi = [(self.GRID_WIDTH // 2, self.GRID_HEIGHT // 2)]
        self.direction = (1, 0)  # (dx, dy) - moving right
        self.next_direction = (1, 0)
        
        # Place first food
        self.place_food()
        
        self.score = 0
        self.old_score = 0
        self.state = self.PLAYING
        self.move_timer = 0
        self.needs_full_redraw = True
        self.needs_score_update = False
        self.old_tail_position = None
        self.old_food_position = None
        
    def place_food(self):
        """Place food at a random empty position"""
        # Store old food position for clearing
        self.old_food_position = getattr(self, 'food', None)
        
        while True:
            x = random.randint(0, self.GRID_WIDTH - 1)
            y = random.randint(0, self.GRID_HEIGHT - 1)
            if (x, y) not in self.hebi:
                self.food = (x, y)
                break
                
    def start(self):
        """Called when the app starts"""
        self.context["drawing"]["clear_screen"]()
        self.draw_game_full()
        
    def update(self):
        if self.state == self.PLAYING:
            self.move_timer += 1
            if self.move_timer >= self.move_interval:
                self.move_timer = 0
                self.move_hebi()
        
        # Handle different types of updates
        if self.needs_full_redraw:
            if self.state == self.PLAYING:
                self.draw_game_full()
            elif self.state == self.GAME_OVER:
                self.draw_game_over()
            self.needs_full_redraw = False
        elif self.state == self.PLAYING:
            # Selective updates for playing state
            if self.needs_score_update:
                self.update_score_area()
                self.needs_score_update = False

    def move_hebi(self):
        """Move the hebi one step"""
        # Update direction
        self.direction = self.next_direction
        
        # Calculate new head position
        head_x, head_y = self.hebi[0]
        new_x = head_x + self.direction[0]
        new_y = head_y + self.direction[1]
        
        # Check wall collision
        if (new_x < 0 or new_x >= self.GRID_WIDTH or 
            new_y < 0 or new_y >= self.GRID_HEIGHT):
            self.game_over()
            return
            
        # Check self collision
        if (new_x, new_y) in self.hebi:
            self.game_over()
            return
            
        # Store old tail position before modifying hebi
        self.old_tail_position = self.hebi[-1] if len(self.hebi) > 0 else None
        
        # Add new head
        new_head = (new_x, new_y)
        self.hebi.insert(0, new_head)
        
        # Check if food eaten
        food_eaten = False
        if new_head == self.food:
            # play food eaten sound
            self.play_sfx(self.path + "bite.wav")
            self.old_score = self.score
            self.score += 1
            self.needs_score_update = True
            food_eaten = True
            self.place_food()
            # Speed up slightly
            if self.move_interval > 3:
                self.move_interval = max(3, self.move_interval - 1)
        
        if not food_eaten:
            # Remove tail if no food eaten
            self.hebi.pop()
        else:
            # If food was eaten, don't clear tail (snake grows)
            self.old_tail_position = None
            
        # Update the game display with selective drawing
        self.update_snake_movement(new_head, food_eaten)
            
    def game_over(self):
        """Handle game over"""
        self.state = self.GAME_OVER
        self.run_tts(f"Game over! Your score was {self.score}", background=True)
        self.needs_full_redraw = True
        
    def update_snake_movement(self, new_head, food_eaten):
        """Update only the areas that changed during snake movement"""
        self.context["drawing"]["begin_batch"]()
        
        # Clear old tail position if snake didn't grow
        if self.old_tail_position and not food_eaten:
            tail_x, tail_y = self.old_tail_position
            pixel_x = tail_x * self.CELL_SIZE
            pixel_y = tail_y * self.CELL_SIZE
            self.context["drawing"]["draw_area"](pixel_x, pixel_y, self.CELL_SIZE, self.CELL_SIZE, 0)
        
        # Draw new head
        head_x, head_y = new_head
        pixel_x = head_x * self.CELL_SIZE
        pixel_y = head_y * self.CELL_SIZE
        self.context["drawing"]["draw_area"](pixel_x, pixel_y, self.CELL_SIZE, self.CELL_SIZE, 255)
        
        # Clear old food position if food was eaten, but only if snake head isn't there
        if food_eaten and self.old_food_position and self.old_food_position != new_head:
            old_food_x, old_food_y = self.old_food_position
            pixel_x = old_food_x * self.CELL_SIZE
            pixel_y = old_food_y * self.CELL_SIZE
            self.context["drawing"]["draw_area"](pixel_x, pixel_y, self.CELL_SIZE, self.CELL_SIZE, 0)
            
        # Draw new food position (only if it's not where the snake head is)
        if self.food != new_head:
            food_x, food_y = self.food
            pixel_x = food_x * self.CELL_SIZE
            pixel_y = food_y * self.CELL_SIZE
            self.context["drawing"]["draw_area"](pixel_x + 1, pixel_y + 1, self.CELL_SIZE - 2, self.CELL_SIZE - 2, 255)
        
        self.context["drawing"]["end_batch"]()
        
    def update_score_area(self):
        """Update only the score display area"""
        self.context["drawing"]["begin_batch"]()
        
        font = self.context["fonts"]["small"]
        font_text = f"{self.score}"
        font_width, font_height = self.context["get_text_size"](font_text, font)
        
        # Clear the entire score area (including old outline)
        old_font_text = f"{self.old_score}"
        old_font_width, old_font_height = self.context["get_text_size"](old_font_text, font)
        clear_width = max(4 + font_width, 4 + old_font_width) + 2  # Extra padding for safety
        clear_height = max(4 + font_height, 4 + old_font_height) + 2
        self.context["drawing"]["draw_area"](0, 0, clear_width, clear_height, 0)
        
        # Draw background box for score
        self.context["drawing"]["draw_area"](1, 1, 4 + font_width, 4 + font_height, 0)
        # Draw box outline
        for i in range(4 + font_width):
            self.context["drawing"]["draw_area"](1 + i, 1, 1, 1, 255)  # Top edge
            self.context["drawing"]["draw_area"](1 + i, 4 + font_height, 1, 1, 255)  # Bottom edge
        for i in range(4 + font_height):
            self.context["drawing"]["draw_area"](1, 1 + i, 1, 1, 255)  # Left edge
            self.context["drawing"]["draw_area"](4 + font_width, 1 + i, 1, 1, 255)  # Right edge
        
        # Draw score text
        self.context["drawing"]["draw_text"](font_text, 3, 3, font)
        
        self.context["drawing"]["end_batch"]()
        
    def draw_game_full(self):
        """Draw the complete game state (full redraw)"""
        self.context["drawing"]["begin_batch"]()
        
        # Draw hebi segments
        for segment in self.hebi:
            x, y = segment
            pixel_x = x * self.CELL_SIZE
            pixel_y = y * self.CELL_SIZE
            self.context["drawing"]["draw_area"](pixel_x, pixel_y, self.CELL_SIZE, self.CELL_SIZE, 255)
            
        # Draw food (slightly smaller for visual distinction)
        food_x, food_y = self.food
        pixel_x = food_x * self.CELL_SIZE
        pixel_y = food_y * self.CELL_SIZE
        self.context["drawing"]["draw_area"](pixel_x + 1, pixel_y + 1, self.CELL_SIZE - 2, self.CELL_SIZE - 2, 255)
        
        # Draw score in corner with background box
        font = self.context["fonts"]["small"]
        font_text = f"{self.score}"
        font_width, font_height = self.context["get_text_size"](font_text, font)
        
        # Draw background box for score
        self.context["drawing"]["draw_area"](1, 1, 4 + font_width, 4 + font_height, 0)
        # Draw box outline
        for i in range(4 + font_width):
            self.context["drawing"]["draw_area"](1 + i, 1, 1, 1, 255)  # Top edge
            self.context["drawing"]["draw_area"](1 + i, 4 + font_height, 1, 1, 255)  # Bottom edge
        for i in range(4 + font_height):
            self.context["drawing"]["draw_area"](1, 1 + i, 1, 1, 255)  # Left edge
            self.context["drawing"]["draw_area"](4 + font_width, 1 + i, 1, 1, 255)  # Right edge
        
        # Draw score text
        self.context["drawing"]["draw_text"](font_text, 3, 3, font)
        
        self.context["drawing"]["end_batch"]()
        
    def draw_game_over(self):
        """Draw game over screen"""
        self.context["drawing"]["begin_batch"]()
        
        font = self.context["fonts"]["small"]
        small_font = self.context["fonts"]["default"]
        
        y = 2
        
        # Game Over text
        game_over_text = "GAME OVER"
        text_width, text_height = self.context["get_text_size"](game_over_text, font)
        self.context["drawing"]["draw_text"](game_over_text, int(64 - text_width/2), y, font)
        y += text_height + 2  # Move down after game over text
        
        # Score
        score_text = f"Score: {self.score}"
        score_width, score_height = self.context["get_text_size"](score_text, small_font)
        self.context["drawing"]["draw_text"](score_text, int(64 - score_width/2), y, small_font)
        y += score_height + 2  # Move down after score text

        # Instructions
        restart_text = "R: Restart"
        restart_width, restart_height = self.context["get_text_size"](restart_text, small_font)
        self.context["drawing"]["draw_text"](restart_text, int(64 - restart_width/2), y, small_font)
        y += restart_height + 2  # Move down after restart text
        
        exit_text = "ESC: Exit"
        exit_width, exit_height = self.context["get_text_size"](exit_text, small_font)
        self.context["drawing"]["draw_text"](exit_text, int(64 - exit_width/2), y, small_font)
        
        self.context["drawing"]["end_batch"]()
        
    def onkeydown(self, keycode):
        """Handle key press events"""
        # Mark for redraw on input that changes game state
        
        if self.state == self.PLAYING:
            # Movement controls
            direction_changed = False
            if keycode == "KEY_UP" or keycode == "KEY_W":
                if self.direction != (0, 1):  # Can't reverse into self
                    self.next_direction = (0, -1)
                    direction_changed = True
            elif keycode == "KEY_DOWN" or keycode == "KEY_S":
                if self.direction != (0, -1):
                    self.next_direction = (0, 1)
                    direction_changed = True
            elif keycode == "KEY_LEFT" or keycode == "KEY_A":
                if self.direction != (1, 0):
                    self.next_direction = (-1, 0)
                    direction_changed = True
            elif keycode == "KEY_RIGHT" or keycode == "KEY_D":
                if self.direction != (-1, 0):
                    self.next_direction = (1, 0)
                    direction_changed = True
            elif keycode == "KEY_SPACE":
                self.state = self.PAUSED
                self.run_tts("Game paused", background=True)
                self.needs_full_redraw = True  # Need to show pause state
                
        elif self.state == self.PAUSED:
            if keycode == "KEY_SPACE":
                self.state = self.PLAYING
                self.run_tts("Game resumed", background=True)
                self.needs_full_redraw = True  # Need to show play state
                
        elif self.state == self.GAME_OVER:
            if keycode == "KEY_R":
                self.reset_game()
                # reset_game() sets needs_full_redraw = True
                
        # Global controls
        if keycode == "KEY_ESC":
            # Save this app as last launched when returning to launcher
            user_prefs = self.context.get("user_preferences")
            if user_prefs:
                user_prefs.set_last_launched_app("hebi")
                
            self.context["app_manager"].swap_app_async("hebi", "launcher", update_rate_hz=20.0, delay=0.1)
            
    def onkeyup(self, keycode):
        """Handle key release events"""
        pass
        
    def stop(self):
        """Called when the app stops"""
        pass
