from interfaces import AppBase
import math
from PIL import Image, ImageDraw

class App(AppBase):
    # Sprite lookup table: each entry is a list of strings (sprite rows)
    SPRITE_TABLE = [
        [  # 0: smiley
            '  .  ',
            ' .#. ',
            '.#.#.',
            '.###.',
            '.....',
        ],
        [  # 1: ghost
            ' ### ',
            '#.#.#',
            '#####',
            '#.#.#',
            '#   #',
        ],
        [  # 2: diamond
            '   .   ',
            '  .#.  ',
            ' .###. ',
            '.#####.',
            ' .###. ',
            '  .#.  ',
            '   .   ',
        ],
    ]

    MINIMAP_SIZE = 20  # Smaller minimap size in pixels
    MINIMAP_MARGIN = 2

    FOG_START = 16  # Distance before fog starts
    # 4x4 Bayer matrix for ordered dithering
    BAYER_4x4 = [
        [ 0,  8,  2, 10],
        [12,  4, 14,  6],
        [ 3, 11,  1,  9],
        [15,  7, 13,  5],
    ]

    def __init__(self, context):
        super().__init__(context)
        self.draw = context["drawing"]  # Use new region-based drawing system
        self.width = 128
        self.height = 64
        self.TILE = 8
        self.MAP = [
            '############',
            '#..........#',
            '#..##..##..#',
            '#..........#',
            '#.2........#',
            '###..#######',
            '#........###',
            '#.....0..###',
            '#........###',
            '############',
        ]
        self.FOV = math.pi / 3
        self.HALF_FOV = self.FOV / 2
        self.NUM_RAYS = 60
        self.MAX_DEPTH = 120
        self.DELTA_ANGLE = self.FOV / self.NUM_RAYS
        self.DIST = self.NUM_RAYS / (2 * math.tan(self.HALF_FOV))
        self.PROJ_COEFF = 2 * self.DIST * self.TILE
        self.SCALE = self.width // self.NUM_RAYS
        self.player_pos = [self.TILE + self.TILE // 2, self.TILE + self.TILE // 2]
        self.player_angle = 0
        self.bg_color = 255
        self.needs_redraw = True
        self.held_keys = context["pressed_keys"]

        # Multiple sprite positions: placed via {0}, {1}, ... in the MAP
        self.sprite_positions = []  # List of (x, y, sprite_idx) for each sprite
        map_rows = []
        for j, row in enumerate(self.MAP):
            new_row = ''
            i = 0  # column index in the logical map
            k = 0  # index in the string
            while k < len(row):
                c = row[k]
                if c.isdigit():
                    idx = int(c)
                    self.sprite_positions.append((i * self.TILE + self.TILE // 2, j * self.TILE + self.TILE // 2, idx))
                    new_row += '.'
                    i += 1
                    k += 1
                    continue
                new_row += c
                if c != '#':
                    i += 1
                k += 1
            map_rows.append(new_row)
        self.MAP = map_rows

    def mapping(self, a, b):
        return int(a // self.TILE), int(b // self.TILE)

    def ray_casting(self, draw, player_pos, player_angle):
        # --- 1. Raycast walls, store wall depths for sprite occlusion ---
        cur_angle = player_angle - self.HALF_FOV
        wall_depths = [self.MAX_DEPTH] * self.NUM_RAYS
        for ray in range(self.NUM_RAYS):
            sin_a = math.sin(cur_angle)
            cos_a = math.cos(cur_angle)
            for depth in range(self.MAX_DEPTH):
                x = player_pos[0] + depth * cos_a
                y = player_pos[1] + depth * sin_a
                i, j = self.mapping(x, y)
                if self.MAP[j][i] == '#':
                    depth_corr = depth * math.cos(player_angle - cur_angle)
                    proj_height = self.PROJ_COEFF / (depth_corr + 0.0001)
                    y0 = int(self.height // 2 - proj_height // 2)
                    y1 = int(self.height // 2 + proj_height // 2)
                    # Draw horizontal white border at the top of the wall
                    if y0 > 0:
                        for sx in range(self.SCALE):
                            draw.point((ray * self.SCALE + sx, y0), fill=1)
                    # Draw horizontal white border at the bottom of the wall
                    if y1-1 < self.height:
                        for sx in range(self.SCALE):
                            draw.point((ray * self.SCALE + sx, y1-1), fill=1)
                    if depth < self.FOG_START:
                        # No fog, solid wall
                        for sx in range(self.SCALE):
                            draw.line([(ray * self.SCALE + sx, y0+1), (ray * self.SCALE + sx, y1-2)], fill=1)
                    else:
                        # Fog: further walls are more dithered (less visible)
                        fog = min(1.0, max(0.0, ((depth - self.FOG_START) / (self.MAX_DEPTH - self.FOG_START))))
                        for sx in range(self.SCALE):
                            for y in range(y0+1, y1-1):
                                bx = (ray * self.SCALE + sx) % 4
                                by = y % 4
                                threshold = self.BAYER_4x4[by][bx] / 16.0
                                if fog < threshold:
                                    draw.point((ray * self.SCALE + sx, y), fill=1)
                    wall_depths[ray] = depth_corr
                    break  # Stop at first wall hit
            cur_angle += self.DELTA_ANGLE

        # --- 2. Draw all sprites (billboarded, always face player) ---
        for sprite_x, sprite_y, sprite_idx in self.sprite_positions:
            dx = sprite_x - player_pos[0]
            dy = sprite_y - player_pos[1]
            dist_to_sprite = math.hypot(dx, dy)
            angle_to_sprite = math.atan2(dy, dx)
            rel_angle = angle_to_sprite - player_angle
            while rel_angle > math.pi:
                rel_angle -= 2 * math.pi
            while rel_angle < -math.pi:
                rel_angle += 2 * math.pi
            if abs(rel_angle) < self.HALF_FOV and dist_to_sprite > 0.5:
                # Sprite scaling by distance
                if dist_to_sprite > 80:
                    continue  # Too far, don't draw
                elif dist_to_sprite > 40:
                    px_per_sprite = 1
                    py_per_sprite = 1
                else:
                    px_per_sprite = 2
                    py_per_sprite = 2

                # Lookup sprite by index, fallback to first sprite if out of range
                sprite = self.SPRITE_TABLE[sprite_idx] if 0 <= sprite_idx < len(self.SPRITE_TABLE) else self.SPRITE_TABLE[0]
                sprite_size_y = len(sprite)
                sprite_size_x = len(sprite[0])
                sprite_w = px_per_sprite * sprite_size_x
                sprite_h = py_per_sprite * sprite_size_y

                ray_float = (rel_angle + self.HALF_FOV) / self.DELTA_ANGLE
                sprite_center_x = ray_float * self.SCALE
                sprite_left = sprite_center_x - sprite_w / 2
                sprite_right = sprite_center_x + sprite_w / 2
                y_center = self.height // 2
                for sx in range(sprite_size_x):
                    for sy in range(sprite_size_y):
                        char = sprite[sy][sx]
                        if char != ' ':
                            x0 = sprite_left + sx * px_per_sprite
                            x1 = x0 + px_per_sprite
                            y0 = y_center - sprite_h // 2 + sy * py_per_sprite
                            y1 = y0 + py_per_sprite
                            ix0 = max(int(round(x0)), 0)
                            ix1 = min(int(round(x1)), self.width)
                            iy0 = max(int(round(y0)), 0)
                            iy1 = min(int(round(y1)), self.height)
                            if ix1 <= ix0 or iy1 <= iy0:
                                continue
                            for px in range(ix0, ix1):
                                if px < sprite_left or px >= sprite_right:
                                    continue
                                ray = px // self.SCALE
                                if 0 <= ray < self.NUM_RAYS and dist_to_sprite <= wall_depths[ray]:
                                    for py in range(iy0, iy1):
                                        draw.point((px, py), fill=1 if char == '#' else 0)

    def start(self):
        self.needs_redraw = True
        self.draw_frame()

    def update(self):
        moved = False
        speed = 2
        next_x, next_y = self.player_pos[0], self.player_pos[1]
        if "KEY_LEFT" in self.held_keys or "KEY_A" in self.held_keys:
            self.player_angle -= 0.08
            moved = True
        if "KEY_RIGHT" in self.held_keys or "KEY_D" in self.held_keys:
            self.player_angle += 0.08
            moved = True
        if "KEY_UP" in self.held_keys or "KEY_W" in self.held_keys:
            next_x += speed * math.cos(self.player_angle)
            next_y += speed * math.sin(self.player_angle)
            moved = True
        if "KEY_DOWN" in self.held_keys or "KEY_S" in self.held_keys:
            next_x -= speed * math.cos(self.player_angle)
            next_y -= speed * math.sin(self.player_angle)
            moved = True
        # Collision detection: only update position if not colliding with wall
        i, j = int(next_x // self.TILE), int(next_y // self.TILE)
        if self.MAP[j][i] != '#':
            self.player_pos[0], self.player_pos[1] = next_x, next_y
        if moved:
            self.needs_redraw = True
        if self.needs_redraw:
            self.draw_frame()
            self.needs_redraw = False

    def draw_frame(self):
        self.draw["begin_batch"]()
        try:
            self.draw["clear_screen"]()
            img = Image.new("1", (self.width, self.height), 0)
            draw = ImageDraw.Draw(img)
            self.ray_casting(draw, self.player_pos, self.player_angle)
            self.draw_minimap(draw)
            self.draw["draw_image"](img, 0, 0)
        finally:
            self.draw["end_batch"]()

    def draw_minimap(self, draw):
        map_rows = len(self.MAP)
        map_cols = len(self.MAP[0])
        size = self.MINIMAP_SIZE
        margin = self.MINIMAP_MARGIN
        cell_w = (size - 2 * margin) / map_cols
        cell_h = (size - 2 * margin) / map_rows

        # Draw map outline
        draw.rectangle([0, 0, size-1, size-1], outline=1, fill=0)

        # Draw map cells
        for j, row in enumerate(self.MAP):
            for i, cell in enumerate(row):
                if cell == '#':
                    x0 = int(margin + i * cell_w)
                    y0 = int(margin + j * cell_h)
                    x1 = int(margin + (i+1) * cell_w - 1)
                    y1 = int(margin + (j+1) * cell_h - 1)
                    draw.rectangle([x0, y0, x1, y1], fill=1)

        # Draw player position
        px = self.player_pos[0] / (self.TILE * map_cols) * (size - 2 * margin) + margin
        py = self.player_pos[1] / (self.TILE * map_rows) * (size - 2 * margin) + margin
        pr = max(1, int(min(cell_w, cell_h) // 3))
        draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=1)

        # Draw player direction
        dir_len = pr * 3
        dx = math.cos(self.player_angle) * dir_len
        dy = math.sin(self.player_angle) * dir_len
        draw.line([px, py, px + dx, py + dy], fill=1)

    def onkeydown(self, keycode):
        if keycode == "KEY_ESC":
            self.context["app_manager"].swap_app_async("doom_clone", "launcher", update_rate_hz=20.0, delay=0.1)

    def onkeyup(self, keycode):
        pass
