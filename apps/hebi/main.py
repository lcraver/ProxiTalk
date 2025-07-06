from interfaces import AppBase
import random
import time
from PIL import Image, ImageDraw

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.display_queue = context["display_queue"]
        self.play_sfx = context["play_sfx"]
        self.run_tts = context["run_tts"]
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
        self.move_interval = 10  # Move every 10 ticks (0.5 seconds at 20Hz)
        
    def reset_game(self):
        """Reset the game to initial state"""
        # hebi starts in the middle, moving right
        self.hebi = [(self.GRID_WIDTH // 2, self.GRID_HEIGHT // 2)]
        self.direction = (1, 0)  # (dx, dy) - moving right
        self.next_direction = (1, 0)
        
        # Place first food
        self.place_food()
        
        self.score = 0
        self.state = self.PLAYING
        self.move_timer = 0
        
    def place_food(self):
        """Place food at a random empty position"""
        while True:
            x = random.randint(0, self.GRID_WIDTH - 1)
            y = random.randint(0, self.GRID_HEIGHT - 1)
            if (x, y) not in self.hebi:
                self.food = (x, y)
                break
                
    def start(self):
        """Called when the app starts"""
        self.draw_game()
        
    def update(self):
        if self.state == self.PLAYING:
            self.move_timer += 1
            if self.move_timer >= self.move_interval:
                self.move_timer = 0
                self.move_hebi()
                if self.state == self.PLAYING:  # Only draw if still playing
                    self.draw_game()

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
            
        # Add new head
        new_head = (new_x, new_y)
        self.hebi.insert(0, new_head)
        
        # Check if food eaten
        if new_head == self.food:
            # play food eaten sound
            self.play_sfx(self.path + "bite.wav")
            self.score += 1
            self.place_food()
            # Speed up slightly
            if self.move_interval > 3:
                self.move_interval = max(3, self.move_interval - 1)
        else:
            # Remove tail if no food eaten
            self.hebi.pop()
            
    def game_over(self):
        """Handle game over"""
        self.state = self.GAME_OVER
        self.run_tts(f"Game over! Your score was {self.score}", background=True)
        self.draw_game_over()
        
    def draw_game(self):
        """Draw the current game state"""
        # Create a 128x64 image
        img = Image.new("1", (128, 64), 0)
        draw = ImageDraw.Draw(img)
        
        # Draw hebi
        for segment in self.hebi:
            x, y = segment
            pixel_x = x * self.CELL_SIZE
            pixel_y = y * self.CELL_SIZE
            draw.rectangle([pixel_x, pixel_y, pixel_x + self.CELL_SIZE - 1, pixel_y + self.CELL_SIZE - 1], fill=1)
            
        # Draw food (blinking effect)
        food_x, food_y = self.food
        pixel_x = food_x * self.CELL_SIZE
        pixel_y = food_y * self.CELL_SIZE
        # Make food slightly smaller for visual distinction
        draw.rectangle([pixel_x + 1, pixel_y + 1, pixel_x + self.CELL_SIZE - 2, pixel_y + self.CELL_SIZE - 2], fill=1)
        
        # Draw score in corner
        font = self.context["fonts"]["small"]
        font_text = f"{self.score}"
        font_width, font_height = draw.textsize(font_text, font=font)
        
        # draw box around score based on font size
        draw.rectangle([1, 1, 3 + font_width, 3 + font_height], outline=1, fill=0)
        draw.text((3, 2), font_text, font=font, fill=1)

        # Send to display
        self.display_queue.put(("clear_base",))
        self.display_queue.put(("draw_base_image", img, 0, 0))
        
    def draw_game_over(self):
        """Draw game over screen"""
        print("Drawing game over screen", flush=True)
        img = Image.new("1", (128, 64), 0)
        draw = ImageDraw.Draw(img)
        
        font = self.context["fonts"]["bold"]
        small_font = self.context["fonts"]["default"]
        
        y = 2
        
        # Game Over text
        game_over_text = "GAME OVER"
        text_width, text_height = draw.textsize(game_over_text, font=font)
        draw.text((64 - text_width/2, y), game_over_text, font=font, fill=1)
        y += text_height + 2  # Move down after game over text
        
        # Score
        score_text = f"Score: {self.score}"
        score_width, score_height = draw.textsize(score_text, font=small_font)
        draw.text((64 - score_width/2, y), score_text, font=small_font, fill=1)
        y += score_height + 2  # Move down after score text

        # Instructions
        restart_text = "R: Restart"
        restart_width, restart_height = draw.textsize(restart_text, font=small_font)
        draw.text((64 - restart_width/2, y), restart_text, font=small_font, fill=1)
        y += restart_height + 2  # Move down after restart text
        
        exit_text = "ESC: Exit"
        exit_width, exit_height = draw.textsize(exit_text, font=small_font)
        draw.text((64 - exit_width/2, y), exit_text, font=small_font, fill=1)
        # Send to display
        self.display_queue.put(("clear_base",))
        self.display_queue.put(("draw_base_image", img, 0, 0))
        
    def onkeydown(self, keycode):
        """Handle key press events"""
        if self.state == self.PLAYING:
            # Movement controls
            if keycode == "KEY_UP" or keycode == "KEY_W":
                if self.direction != (0, 1):  # Can't reverse into self
                    self.next_direction = (0, -1)
            elif keycode == "KEY_DOWN" or keycode == "KEY_S":
                if self.direction != (0, -1):
                    self.next_direction = (0, 1)
            elif keycode == "KEY_LEFT" or keycode == "KEY_A":
                if self.direction != (1, 0):
                    self.next_direction = (-1, 0)
            elif keycode == "KEY_RIGHT" or keycode == "KEY_D":
                if self.direction != (-1, 0):
                    self.next_direction = (1, 0)
            elif keycode == "KEY_SPACE":
                self.state = self.PAUSED
                self.run_tts("Game paused", background=True)
                
        elif self.state == self.PAUSED:
            if keycode == "KEY_SPACE":
                self.state = self.PLAYING
                self.run_tts("Game resumed", background=True)
                
        elif self.state == self.GAME_OVER:
            if keycode == "KEY_R":
                self.reset_game()
                self.draw_game()
                
        # Global controls
        if keycode == "KEY_ESC":
            self.display_queue.put(("set_screen", "Launcher", "Returning to launcher..."))
            self.context["app_manager"].swap_app_async("hebi", "launcher", update_rate_hz=20.0, delay=0.1)
            
    def onkeyup(self, keycode):
        """Handle key release events"""
        pass
        
    def stop(self):
        """Called when the app stops"""
        pass
