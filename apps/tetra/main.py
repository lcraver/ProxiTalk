from interfaces import AppBase
import random
import time
from PIL import Image, ImageDraw

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.display_queue = context["display_queue"]
        self.play_sfx = context["audio"]["play_sfx"]
        self.run_tts = context["run_tts"]
        self.path = context["app_path"]
        
        # Game constants
        self.GRID_WIDTH = 10
        self.GRID_HEIGHT = 20
        self.CELL_SIZE = 3  # 3x3 pixels per cell (30x60 pixels for the play area)
        self.GRID_OFFSET_X = (128 - self.GRID_WIDTH * self.CELL_SIZE) // 2  # Center horizontally
        self.GRID_OFFSET_Y = 2  # Small offset from top
        
        # Tetromino shapes (4x4 grids)
        self.SHAPES = {
            'I': [
                [0, 0, 0, 0],
                [1, 1, 1, 1],
                [0, 0, 0, 0],
                [0, 0, 0, 0]
            ],
            'O': [
                [0, 0, 0, 0],
                [0, 1, 1, 0],
                [0, 1, 1, 0],
                [0, 0, 0, 0]
            ],
            'T': [
                [0, 0, 0, 0],
                [0, 1, 0, 0],
                [1, 1, 1, 0],
                [0, 0, 0, 0]
            ],
            'S': [
                [0, 0, 0, 0],
                [0, 1, 1, 0],
                [1, 1, 0, 0],
                [0, 0, 0, 0]
            ],
            'Z': [
                [0, 0, 0, 0],
                [1, 1, 0, 0],
                [0, 1, 1, 0],
                [0, 0, 0, 0]
            ],
            'J': [
                [0, 0, 0, 0],
                [1, 0, 0, 0],
                [1, 1, 1, 0],
                [0, 0, 0, 0]
            ],
            'L': [
                [0, 0, 0, 0],
                [0, 0, 1, 0],
                [1, 1, 1, 0],
                [0, 0, 0, 0]
            ]
        }
        
        # Game states
        self.PLAYING = 0
        self.GAME_OVER = 1
        self.PAUSED = 2
        
        # Initialize game
        self.reset_game()
        
        # Timing
        self.drop_timer = 0
        self.drop_interval = 20  # Drop every 20 ticks initially
        self.fast_drop_active = False  # Track if fast drop is active
        
        # Performance optimization
        self.needs_redraw = True  # Flag to control when to redraw
        
    def reset_game(self):
        """Reset the game to initial state"""
        # Initialize empty grid
        self.grid = [[0 for _ in range(self.GRID_WIDTH)] for _ in range(self.GRID_HEIGHT)]
        
        # Game state
        self.score = 0
        self.lines_cleared = 0
        self.level = 1
        self.state = self.PLAYING
        self.drop_timer = 0
        self.fast_drop_active = False  # Reset fast drop state
        self.needs_redraw = True  # Force redraw after reset
        
        # Current piece
        self.current_piece = self.spawn_piece()
        self.next_piece = self.spawn_piece()
        
    def spawn_piece(self):
        """Spawn a new tetromino piece"""
        shape_key = random.choice(list(self.SHAPES.keys()))
        return {
            'shape': self.SHAPES[shape_key],
            'x': self.GRID_WIDTH // 2 - 2,  # Center horizontally
            'y': 0,
            'type': shape_key
        }
        
    def rotate_piece(self, piece):
        """Rotate a piece 90 degrees clockwise"""
        shape = piece['shape']
        # Transpose and reverse each row
        rotated = []
        for i in range(4):
            row = []
            for j in range(4):
                row.append(shape[3-j][i])
            rotated.append(row)
        return rotated
        
    def is_valid_position(self, piece, dx=0, dy=0, shape=None):
        """Check if a piece position is valid"""
        if shape is None:
            shape = piece['shape']
            
        for y in range(4):
            for x in range(4):
                if shape[y][x]:
                    new_x = piece['x'] + x + dx
                    new_y = piece['y'] + y + dy
                    
                    # Check boundaries
                    if new_x < 0 or new_x >= self.GRID_WIDTH or new_y >= self.GRID_HEIGHT:
                        return False
                    
                    # Check collision with placed pieces (ignore if above grid)
                    if new_y >= 0 and self.grid[new_y][new_x]:
                        return False
                        
        return True
        
    def place_piece(self, piece):
        """Place a piece on the grid"""
        for y in range(4):
            for x in range(4):
                if piece['shape'][y][x]:
                    grid_x = piece['x'] + x
                    grid_y = piece['y'] + y
                    if 0 <= grid_y < self.GRID_HEIGHT and 0 <= grid_x < self.GRID_WIDTH:
                        self.grid[grid_y][grid_x] = 1
                        
    def clear_lines(self):
        """Clear completed lines and return the number cleared"""
        lines_to_clear = []
        
        # Find completed lines
        for y in range(self.GRID_HEIGHT):
            if all(self.grid[y][x] for x in range(self.GRID_WIDTH)):
                lines_to_clear.append(y)
                
        # Remove completed lines
        for y in lines_to_clear:
            del self.grid[y]
            self.grid.insert(0, [0 for _ in range(self.GRID_WIDTH)])
            
        # Update score and level
        if lines_to_clear:
            lines_count = len(lines_to_clear)
            self.lines_cleared += lines_count
            
            # Score based on lines cleared at once
            line_scores = {1: 100, 2: 300, 3: 500, 4: 800}
            self.score += line_scores.get(lines_count, 100) * self.level
            
            # Level up every 10 lines
            new_level = (self.lines_cleared // 10) + 1
            if new_level > self.level:
                self.level = new_level
                self.drop_interval = max(2, 20 - (self.level - 1) * 2)  # Speed up
                self.play_sfx(self.path + "level_up.wav")
                self.run_tts(f"Level {self.level}!", background=True)
                
        return len(lines_to_clear)
        
    def start(self):
        """Called when the app starts"""
        self.needs_redraw = True
        
    def update(self):
        if self.state == self.PLAYING:
            self.drop_timer += 1
            if self.drop_timer >= self.drop_interval:
                self.drop_timer = 0
                self.drop_piece()
                
        # Only redraw when necessary
        if self.needs_redraw and self.state == self.PLAYING:
            self.draw_game()
            self.needs_redraw = False

    def drop_piece(self):
        """Drop the current piece one row"""
        if self.is_valid_position(self.current_piece, dy=1):
            self.current_piece['y'] += 1
            self.needs_redraw = True
        else:
            # Piece landed
            self.place_piece(self.current_piece)
            
            # Clear lines
            lines_cleared = self.clear_lines()
            if lines_cleared > 0:
                if lines_cleared == 4:
                    self.play_sfx(self.path + "tetra.wav")
                    self.run_tts("Oh baby a Tetra!", background=True)
                else:
                    self.play_sfx(self.path + "line_clear.wav")
            else:
                # Only play drop sound if no lines were cleared
                self.play_sfx(self.path + "drop.wav")
            
            # Spawn next piece
            self.current_piece = self.next_piece
            self.next_piece = self.spawn_piece()
            self.needs_redraw = True
            
            # Check game over
            if not self.is_valid_position(self.current_piece):
                self.game_over()
                
    def game_over(self):
        self.state = self.GAME_OVER
        self.play_sfx(self.path + "game_over.wav")
        self.run_tts(f"Game over! Final score: {self.score}", background=True)
        self.draw_game_over()
        
    # this should definitely only draw the game itself and not the UI since that update less...
    def draw_game(self):
        img = Image.new("1", (128, 64), 0)
        draw = ImageDraw.Draw(img)
        
        # Draw grid border
        border_x1 = self.GRID_OFFSET_X - 1
        border_y1 = self.GRID_OFFSET_Y - 1
        border_x2 = self.GRID_OFFSET_X + self.GRID_WIDTH * self.CELL_SIZE
        border_y2 = self.GRID_OFFSET_Y + self.GRID_HEIGHT * self.CELL_SIZE
        draw.rectangle([border_x1, border_y1, border_x2, border_y2], outline=1, fill=0)
        
        # Collect all filled cells for batch drawing
        filled_cells = []
        
        # Add placed pieces
        for y in range(self.GRID_HEIGHT):
            for x in range(self.GRID_WIDTH):
                if self.grid[y][x]:
                    filled_cells.append((x, y))
        
        # Add current piece
        if self.current_piece:
            for y in range(4):
                for x in range(4):
                    if self.current_piece['shape'][y][x]:
                        grid_x = self.current_piece['x'] + x
                        grid_y = self.current_piece['y'] + y
                        
                        # Only add if within visible area
                        if (0 <= grid_x < self.GRID_WIDTH and 
                            grid_y >= 0 and grid_y < self.GRID_HEIGHT):
                            filled_cells.append((grid_x, grid_y))
        
        # Draw all filled cells in one go
        for x, y in filled_cells:
            pixel_x = self.GRID_OFFSET_X + x * self.CELL_SIZE
            pixel_y = self.GRID_OFFSET_Y + y * self.CELL_SIZE
            draw.rectangle([pixel_x, pixel_y, 
                          pixel_x + self.CELL_SIZE - 1, 
                          pixel_y + self.CELL_SIZE - 1], fill=1)
        
        # Draw score and level (right side)
        font = self.context["fonts"]["small"]
        score_x = self.GRID_OFFSET_X + self.GRID_WIDTH * self.CELL_SIZE + 3
        
        score_text = f"Score:"
        draw.text((score_x, 5), score_text, font=font, fill=1)
        score_value = f"{self.score}"
        draw.text((score_x, 12), score_value, font=font, fill=1)
        
        level_text = f"Level:"
        draw.text((score_x, 22), level_text, font=font, fill=1)
        level_value = f"{self.level}"
        draw.text((score_x, 29), level_value, font=font, fill=1)
        
        lines_text = f"Lines:"
        draw.text((score_x, 39), lines_text, font=font, fill=1)
        lines_value = f"{self.lines_cleared}"
        draw.text((score_x, 46), lines_value, font=font, fill=1)
        
        # Draw next piece preview (left side)
        next_y = 5
        next_text = "Next:"
        width = draw.textlength(next_text, font=font)
        next_x = border_x1 - width - 1
        draw.text((next_x, next_y), next_text, font=font, fill=1)
        
        # Draw next piece
        if self.next_piece:
            for y in range(4):
                for x in range(4):
                    if self.next_piece['shape'][y][x]:
                        pixel_x = next_x + x * 2
                        pixel_y = next_y + 8 + y * 2
                        draw.rectangle([pixel_x, pixel_y, pixel_x + 1, pixel_y + 1], fill=1)

        # Send to display
        self.display_queue.put(("clear_base",))
        self.display_queue.put(("draw_base_image", img, 0, 0))
        
    def draw_game_over(self):
        img = Image.new("1", (128, 64), 0)
        draw = ImageDraw.Draw(img)
        
        font = self.context["fonts"]["bold"]
        small_font = self.context["fonts"]["default"]
        
        y = 2
        
        # Game Over text
        game_over_text = "GAME OVER"
        text_width, text_height = draw.textsize(game_over_text, font=font)
        draw.text((64 - text_width/2, y), game_over_text, font=font, fill=1)
        y += text_height + 2
        
        # Score
        score_text = f"Score: {self.score}"
        score_width, score_height = draw.textsize(score_text, font=small_font)
        draw.text((64 - score_width/2, y), score_text, font=small_font, fill=1)
        y += score_height + 2
        
        # Level
        level_text = f"Level: {self.level} / {self.lines_cleared}"
        level_width, level_height = draw.textsize(level_text, font=small_font)
        draw.text((64 - level_width/2, y), level_text, font=small_font, fill=1)
        y += level_height + 2
        
        # Instructions
        restart_text = "R: Retry / ESC: Exit"
        restart_width, restart_height = draw.textsize(restart_text, font=small_font)
        draw.text((64 - restart_width/2, y), restart_text, font=small_font, fill=1)
        
        # Send to display
        self.display_queue.put(("clear_base",))
        self.display_queue.put(("draw_base_image", img, 0, 0))
        
    def onkeyup(self, keycode):
        if self.state == self.PLAYING:
            # Movement controls
            if keycode == "KEY_LEFT" or keycode == "KEY_A":
                if self.is_valid_position(self.current_piece, dx=-1):
                    self.current_piece['x'] -= 1
                    self.needs_redraw = True
                    # Reduce move sound frequency to avoid audio lag
                    if hasattr(self, '_last_move_sound') and time.time() - self._last_move_sound < 0.1:
                        pass  # Skip sound if too recent
                    else:
                        self.play_sfx(self.path + "move.wav")
                        self._last_move_sound = time.time()
            elif keycode == "KEY_RIGHT" or keycode == "KEY_D":
                if self.is_valid_position(self.current_piece, dx=1):
                    self.current_piece['x'] += 1
                    self.needs_redraw = True
                    # Reduce move sound frequency to avoid audio lag
                    if hasattr(self, '_last_move_sound') and time.time() - self._last_move_sound < 0.1:
                        pass  # Skip sound if too recent
                    else:
                        self.play_sfx(self.path + "move.wav")
                        self._last_move_sound = time.time()
            elif keycode == "KEY_DOWN" or keycode == "KEY_S":
                # Soft drop
                self.drop_piece()
            elif keycode == "KEY_UP" or keycode == "KEY_W":
                # Rotate piece
                rotated_shape = self.rotate_piece(self.current_piece)
                if self.is_valid_position(self.current_piece, shape=rotated_shape):
                    self.current_piece['shape'] = rotated_shape
                    self.needs_redraw = True
                    self.play_sfx(self.path + "move.wav")
            elif keycode == "KEY_SPACE":
                # Hard drop
                while self.is_valid_position(self.current_piece, dy=1):
                    self.current_piece['y'] += 1
                self.drop_piece()
            elif keycode == "KEY_P":
                self.state = self.PAUSED
                self.run_tts("Game paused", background=True)
                
        elif self.state == self.PAUSED:
            if keycode == "KEY_P" or keycode == "KEY_SPACE":
                self.state = self.PLAYING
                self.needs_redraw = True
                self.run_tts("Game resumed", background=True)
                
        elif self.state == self.GAME_OVER:
            if keycode == "KEY_R":
                self.reset_game()
                
        # Global controls
        if keycode == "KEY_ESC":
            self.display_queue.put(("set_screen", "Launcher", "Returning to launcher..."))
            self.context["app_manager"].swap_app_async("tetra", "launcher", update_rate_hz=20.0, delay=0.1)
            
    def stop(self):
        pass
