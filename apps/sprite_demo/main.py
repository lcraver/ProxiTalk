"""Sprite Demo — a tiny Asteroids clone. KEY_LEFT/KEY_RIGHT rotate the ship,
KEY_SPACE thrusts, KEY_ENTER fires (or restarts after game over). Asteroids
split into smaller ones when shot; clearing a wave spawns a bigger one.

End-to-end example of sprite/timer/geometry working together, leaning much
harder on geometry than the old bouncing-boxes version did:
  - AffineTransform.rotation() turns the ship/asteroid polygons every tick
    (mirrors Playdate's sprite:update() override pattern) and also rotates
    velocity vectors directly (apply_to_vector) when an asteroid splits, so
    the two child rocks scatter apart instead of flying off in a straight
    line.
  - Vector2D drives all motion (thrust acceleration, drag, velocity) instead
    of hand-rolled dx/dy floats.
  - LineSegment.intersects() does the actual bullet-vs-asteroid hit test:
    a fast bullet's rect can hop clean over a thin polygon edge between one
    tick and the next, so each bullet's PATH (previous center -> current
    center) is tested against every edge of the asteroid's current polygon,
    not just an end-of-frame rect overlap.
  - Sprite groups/collides_with_groups still gate the (coarser, rect-based)
    ship-vs-asteroid check the same way the old demo used them for
    player-vs-hazard.

The ship/asteroid wireframes are plain PIL ImageDraw.line() calls baked into
a small per-sprite bitmap and re-drawn every tick (no dirty-rect/rotation
support exists below the Sprite layer -- see sprite.py's own docstring on
redrawing unconditionally each tick), then blitted through the normal
Sprite/SpriteList image path like any other sprite.
"""

from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw

from core_os.apps_runtime.app_base import AppBase

_SHIP_GROUP = 1
_ASTEROID_GROUP = 2
_BULLET_GROUP = 3

_STATUS_HEIGHT = 10
_MAX_LIVES = 3
_WAVE_BASE_ASTEROIDS = 3
_WAVE_MAX_ASTEROIDS = 8

_SHIP_SIZE = 20  # sprite bitmap side, ship center at (size/2, size/2)
_SHIP_NOSE_LEN = 6.0
_SHIP_WING_HALF = 4.0
_SHIP_WING_BACK = 4.0
_SHIP_FLAME_LEN = 4.0
_SHIP_TURN_SPEED = 200.0  # deg/sec
_SHIP_THRUST_ACCEL = 80.0  # px/sec^2
_SHIP_MAX_SPEED = 70.0  # px/sec
_SHIP_DRAG = 0.6  # fraction of velocity shed per second
_SHIP_INVULN_DURATION = 2.0
_SHIP_BLINK_HZ = 8.0

_FIRE_COOLDOWN = 0.25
_MAX_BULLETS = 4
_BULLET_SPEED = 140.0
_BULLET_LIFETIME = 0.9
_BULLET_SIZE = 2

# tier -> (radius, spawn speed range, score value, tier spawned on split)
_ASTEROID_TIERS = {
    "large": (12.0, (10.0, 20.0), 20, "medium"),
    "medium": (7.0, (18.0, 30.0), 50, "small"),
    "small": (4.0, (28.0, 45.0), 100, None),
}
_ASTEROID_VERT_COUNT = 9
_ASTEROID_JAGGEDNESS = 0.35  # vertices vary this fraction below full radius
_ASTEROID_SPIN_RANGE = (-60.0, 60.0)  # deg/sec
_ASTEROID_PAD = 2  # bitmap margin so line-drawing at the rim isn't clipped
_ASTEROID_SPLIT_ANGLE_RANGE = (30.0, 90.0)


def _make_ship_class(sprite_cls, geo):
    """Subclasses whatever Sprite class context["sprite"]["sprite"] hands
    back, rather than importing core_os.packages.sprite.sprite.Sprite
    directly -- apps only ever touch packages through their scoped context
    (see apps_runtime/app_loader.py's ScopedAppContext). Same reason the
    geometry primitives below come from `geo` (context["geometry"]), not a
    module-level import."""
    Vector2D = geo["vector2d"]
    Point = geo["point"]
    AffineTransform = geo["affine_transform"]

    _NOSE = Point(0.0, -_SHIP_NOSE_LEN)
    _LEFT_WING = Point(-_SHIP_WING_HALF, _SHIP_WING_BACK)
    _RIGHT_WING = Point(_SHIP_WING_HALF, _SHIP_WING_BACK)
    _FLAME_TIP = Point(0.0, _SHIP_WING_BACK + _SHIP_FLAME_LEN)
    _UP = Vector2D(0.0, -1.0)
    _HALF = _SHIP_SIZE / 2.0

    def _draw_ship_image(angle_deg, thrusting):
        rot = AffineTransform.rotation(angle_deg)
        nose = rot.apply_to_point(_NOSE)
        left = rot.apply_to_point(_LEFT_WING)
        right = rot.apply_to_point(_RIGHT_WING)
        img = Image.new("1", (_SHIP_SIZE, _SHIP_SIZE))
        draw = ImageDraw.Draw(img)
        to_px = lambda p: (_HALF + p.x, _HALF + p.y)
        draw.line([to_px(nose), to_px(left)], fill=1)
        draw.line([to_px(left), to_px(right)], fill=1)
        draw.line([to_px(right), to_px(nose)], fill=1)
        if thrusting:
            flame = rot.apply_to_point(_FLAME_TIP)
            draw.line([to_px(left), to_px(flame)], fill=1)
            draw.line([to_px(right), to_px(flame)], fill=1)
        return img

    class Ship(sprite_cls):
        def __init__(self, image, cx, cy, screen_width, screen_height):
            super().__init__(image, x=cx - _HALF, y=cy - _HALF)
            self.cx = cx
            self.cy = cy
            self.angle = 0.0
            self.velocity = Vector2D(0.0, 0.0)
            self.turn = 0
            self.thrusting = False
            self.invuln_timer = _SHIP_INVULN_DURATION
            self.screen_width = screen_width
            self.screen_height = screen_height
            self.set_groups([_SHIP_GROUP])
            self.set_collides_with_groups([_ASTEROID_GROUP])

        def facing(self):
            return AffineTransform.rotation(self.angle).apply_to_vector(_UP)

        def nose_point(self):
            f = self.facing()
            return (self.cx + f.dx * _SHIP_NOSE_LEN, self.cy + f.dy * _SHIP_NOSE_LEN)

        def respawn(self):
            self.cx = self.screen_width / 2.0
            self.cy = self.screen_height / 2.0
            self.angle = 0.0
            self.velocity = Vector2D(0.0, 0.0)
            self.thrusting = False
            self.invuln_timer = _SHIP_INVULN_DURATION

        def update(self, dt):
            self.angle = (self.angle + self.turn * _SHIP_TURN_SPEED * dt) % 360.0
            if self.thrusting:
                self.velocity = self.velocity + self.facing() * (_SHIP_THRUST_ACCEL * dt)
                if self.velocity.length() > _SHIP_MAX_SPEED:
                    self.velocity = self.velocity.normalized() * _SHIP_MAX_SPEED
            self.velocity = self.velocity * max(0.0, 1.0 - _SHIP_DRAG * dt)
            self.cx = (self.cx + self.velocity.dx * dt) % self.screen_width
            self.cy = (self.cy + self.velocity.dy * dt) % self.screen_height

            if self.invuln_timer > 0.0:
                self.invuln_timer = max(0.0, self.invuln_timer - dt)
                self.set_visible(int(self.invuln_timer * _SHIP_BLINK_HZ) % 2 == 0)
            else:
                self.set_visible(True)

            self.set_image(_draw_ship_image(self.angle, self.thrusting))
            self.move_to(self.cx - _HALF, self.cy - _HALF)

    return Ship


def _make_asteroid_class(sprite_cls, geo):
    Point = geo["point"]
    AffineTransform = geo["affine_transform"]
    LineSegment = geo["line_segment"]

    class Asteroid(sprite_cls):
        def __init__(self, tier, cx, cy, velocity, screen_width, screen_height):
            radius, _speed_range, score, next_tier = _ASTEROID_TIERS[tier]
            size = int(radius * 2 + _ASTEROID_PAD * 2)
            super().__init__(Image.new("1", (size, size)), x=cx - size / 2.0, y=cy - size / 2.0)
            self.tier = tier
            self.radius = radius
            self.score = score
            self.next_tier = next_tier
            self.cx = cx
            self.cy = cy
            self.velocity = velocity
            self.angle = random.uniform(0.0, 360.0)
            self.spin = random.uniform(*_ASTEROID_SPIN_RANGE)
            self.screen_width = screen_width
            self.screen_height = screen_height
            self.size = size
            jag = _ASTEROID_JAGGEDNESS
            self.local_verts = []
            for i in range(_ASTEROID_VERT_COUNT):
                a = math.radians(360.0 * i / _ASTEROID_VERT_COUNT)
                r = radius * random.uniform(1.0 - jag, 1.0)
                self.local_verts.append(Point(r * math.sin(a), -r * math.cos(a)))
            self.world_edges = []
            self.set_groups([_ASTEROID_GROUP])
            self._refresh()

        def _refresh(self):
            rot = AffineTransform.rotation(self.angle)
            rotated = [rot.apply_to_point(v) for v in self.local_verts]
            half = self.size / 2.0
            img = Image.new("1", (self.size, self.size))
            draw = ImageDraw.Draw(img)
            n = len(rotated)
            world_pts = []
            for i in range(n):
                p0, p1 = rotated[i], rotated[(i + 1) % n]
                draw.line([(half + p0.x, half + p0.y), (half + p1.x, half + p1.y)], fill=1)
                world_pts.append(Point(self.cx + p0.x, self.cy + p0.y))
            self.world_edges = [
                LineSegment(world_pts[i], world_pts[(i + 1) % n]) for i in range(n)
            ]
            self.set_image(img)
            self.move_to(self.cx - half, self.cy - half)

        def update(self, dt):
            self.angle = (self.angle + self.spin * dt) % 360.0
            self.cx = (self.cx + self.velocity.dx * dt) % self.screen_width
            self.cy = (self.cy + self.velocity.dy * dt) % self.screen_height
            self._refresh()

    return Asteroid


def _make_bullet_class(sprite_cls):
    class Bullet(sprite_cls):
        def __init__(self, image, cx, cy, velocity, lifetime):
            super().__init__(image, x=cx - _BULLET_SIZE / 2.0, y=cy - _BULLET_SIZE / 2.0)
            self.cx = cx
            self.cy = cy
            self.prev_cx = cx
            self.prev_cy = cy
            self.velocity = velocity
            self.lifetime = lifetime
            self.set_groups([_BULLET_GROUP])

        def update(self, dt):
            self.prev_cx, self.prev_cy = self.cx, self.cy
            self.cx += self.velocity.dx * dt
            self.cy += self.velocity.dy * dt
            self.lifetime -= dt
            self.move_to(self.cx - _BULLET_SIZE / 2.0, self.cy - _BULLET_SIZE / 2.0)

        def expired(self, screen_width, screen_height):
            # Bullets deliberately do NOT wrap like the ship/asteroids do --
            # a wrapped bullet's prev->current path would draw a bogus
            # segment clear across the screen and could false-positive the
            # LineSegment hit test below.
            return (
                self.lifetime <= 0.0
                or not (0.0 <= self.cx <= screen_width)
                or not (0.0 <= self.cy <= screen_height)
            )

    return Bullet


class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.gfx = context["display_gfx"]
        self.sprite = context["sprite"]
        self.geometry = context["geometry"]
        self.app_control = context["app_control"]
        self.timers = context["timer"]["timer_manager"]()
        self.screen_width = context["screen_width"]
        self.screen_height = context["screen_height"]

        self.sprites = None
        self.ship_cls = None
        self.asteroid_cls = None
        self.bullet_cls = None
        self.ship = None
        self.asteroids = []
        self.bullets = []
        self._bullet_image = None

        self._held_left = False
        self._held_right = False
        self._held_thrust = False
        self._fire_cooldown = 0.0
        self._score = 0
        self._lives = _MAX_LIVES
        self._wave = 1
        self._game_over = False
        self._last_status = None

    # --- setup -----------------------------------------------------------

    def start(self):
        self.gfx["clear_screen"]()

        self.sprites = self.sprite["sprite_list"](layer="base")
        self.ship_cls = _make_ship_class(self.sprite["sprite"], self.geometry)
        self.asteroid_cls = _make_asteroid_class(self.sprite["sprite"], self.geometry)
        self.bullet_cls = _make_bullet_class(self.sprite["sprite"])
        self._bullet_image = Image.new("1", (_BULLET_SIZE, _BULLET_SIZE), 1)

        blank = Image.new("1", (_SHIP_SIZE, _SHIP_SIZE))
        self.ship = self.ship_cls(
            blank, self.screen_width / 2.0, self.screen_height / 2.0, self.screen_width, self.screen_height)
        self.sprites.add(self.ship)

        self.asteroids = []
        self.bullets = []
        self._held_left = False
        self._held_right = False
        self._held_thrust = False
        self._fire_cooldown = 0.0
        self._score = 0
        self._lives = _MAX_LIVES
        self._wave = 1
        self._game_over = False
        self._last_status = None
        self._spawn_wave()
        self._draw_status()

    # --- asteroid spawning/splitting --------------------------------------

    def _spawn_wave(self):
        count = min(_WAVE_BASE_ASTEROIDS + self._wave - 1, _WAVE_MAX_ASTEROIDS)
        for _ in range(count):
            self._spawn_asteroid("large")

    def _spawn_asteroid(self, tier, cx=None, cy=None, velocity=None):
        Vector2D = self.geometry["vector2d"]
        if cx is None or cy is None:
            # Edge-spawn for a fresh wave -- keeps a brand new large rock
            # from ever materializing right on top of the ship.
            side = random.choice(("top", "bottom", "left", "right"))
            if side in ("top", "bottom"):
                cx = random.uniform(0.0, self.screen_width)
                cy = float(_STATUS_HEIGHT) if side == "top" else float(self.screen_height - 1)
            else:
                cx = 0.0 if side == "left" else float(self.screen_width - 1)
                cy = random.uniform(_STATUS_HEIGHT, self.screen_height)
        if velocity is None:
            _radius, speed_range, _score, _next = _ASTEROID_TIERS[tier]
            speed = random.uniform(*speed_range)
            heading = math.radians(random.uniform(0.0, 360.0))
            velocity = Vector2D(math.sin(heading) * speed, -math.cos(heading) * speed)
        asteroid = self.asteroid_cls(tier, cx, cy, velocity, self.screen_width, self.screen_height)
        self.asteroids.append(asteroid)
        self.sprites.add(asteroid)

    def _split_asteroid(self, asteroid):
        self._score += asteroid.score
        if asteroid.next_tier is not None:
            AffineTransform = self.geometry["affine_transform"]
            Vector2D = self.geometry["vector2d"]
            base_dir = asteroid.velocity.normalized()
            if base_dir.length() == 0.0:
                base_dir = Vector2D(0.0, -1.0)
            _radius, speed_range, _score, next_tier = _ASTEROID_TIERS[asteroid.next_tier]
            for sign in (1.0, -1.0):
                offset = sign * random.uniform(*_ASTEROID_SPLIT_ANGLE_RANGE)
                new_dir = AffineTransform.rotation(offset).apply_to_vector(base_dir)
                speed = random.uniform(*speed_range)
                self._spawn_asteroid(asteroid.next_tier, asteroid.cx, asteroid.cy, new_dir * speed)
        self.asteroids.remove(asteroid)
        self.sprites.remove(asteroid)

    # --- firing ------------------------------------------------------------

    def _fire(self):
        if self._fire_cooldown > 0.0 or len(self.bullets) >= _MAX_BULLETS:
            return
        nose_x, nose_y = self.ship.nose_point()
        velocity = self.ship.facing() * _BULLET_SPEED
        bullet = self.bullet_cls(self._bullet_image, nose_x, nose_y, velocity, _BULLET_LIFETIME)
        self.bullets.append(bullet)
        self.sprites.add(bullet)
        self._fire_cooldown = _FIRE_COOLDOWN

    # --- status/game-over text ----------------------------------------------

    def _draw_status(self):
        status = (self._score, self._lives, self._wave)
        if status == self._last_status:
            return
        self._last_status = status
        font = self.gfx["fonts"]["small"]
        self.gfx["clear_area"](0, 0, self.screen_width, _STATUS_HEIGHT)
        self.gfx["draw_text"](
            f"score {self._score}   lives {self._lives}   wave {self._wave}", 0, 0, font=font)

    def _draw_centered(self, text, y, font):
        w, _h = self.gfx["get_text_size"](text, font)
        self.gfx["draw_text"](text, (self.screen_width - w) // 2, y, font=font)

    def _draw_game_over(self):
        font = self.gfx["fonts"]["small"]
        self.gfx["clear_area"](0, _STATUS_HEIGHT, self.screen_width, self.screen_height - _STATUS_HEIGHT)
        mid_y = _STATUS_HEIGHT + (self.screen_height - _STATUS_HEIGHT) / 2
        self._draw_centered("GAME OVER", int(mid_y) - 15, font)
        self._draw_centered(f"score {self._score}", int(mid_y), font)
        self._draw_centered("ENTER to restart", int(mid_y) + 15, font)

    # --- per-tick update ----------------------------------------------------

    def update(self):
        dt = self.timers.tick()
        if self._game_over:
            return

        self.ship.turn = (1 if self._held_right else 0) - (1 if self._held_left else 0)
        self.ship.thrusting = self._held_thrust
        if self._fire_cooldown > 0.0:
            self._fire_cooldown = max(0.0, self._fire_cooldown - dt)

        self.sprites.update_and_draw(dt)

        for bullet in list(self.bullets):
            if bullet.expired(self.screen_width, self.screen_height):
                self.bullets.remove(bullet)
                self.sprites.remove(bullet)

        # Bullet vs asteroid: swept path (prev center -> current center)
        # against every edge of the asteroid's CURRENT polygon, so a bullet
        # moving several pixels a tick can't skip clean over a thin edge
        # the way an end-of-frame rect-overlap check could.
        LineSegment = self.geometry["line_segment"]
        Point = self.geometry["point"]
        for bullet in list(self.bullets):
            path = LineSegment(Point(bullet.prev_cx, bullet.prev_cy), Point(bullet.cx, bullet.cy))
            hit = next(
                (a for a in self.asteroids if any(path.intersects(edge) for edge in a.world_edges)),
                None,
            )
            if hit is not None:
                if bullet in self.bullets:
                    self.bullets.remove(bullet)
                    self.sprites.remove(bullet)
                self._split_asteroid(hit)

        # Ship vs asteroid: coarser rect-overlap check via Sprite groups --
        # good enough at this screen size, unlike the fast/thin bullets above.
        if self.ship.invuln_timer <= 0.0 and self.sprites.overlapping(self.ship):
            self._lives -= 1
            if self._lives <= 0:
                self._lives = 0
                self._game_over = True
                self._draw_status()
                self._draw_game_over()
                return
            self.ship.respawn()

        if not self.asteroids:
            self._wave += 1
            self._spawn_wave()

        self._draw_status()

    def onkeydown(self, keycode):
        if keycode == "KEY_ESC":
            self.app_control.swap_app_async("sprite_demo", "launcher", delay=0.1)
        elif keycode == "KEY_LEFT":
            self._held_left = True
        elif keycode == "KEY_RIGHT":
            self._held_right = True
        elif keycode == "KEY_SPACE":
            self._held_thrust = True
        elif keycode == "KEY_ENTER":
            if self._game_over:
                self.start()
            else:
                self._fire()

    def onkeyup(self, keycode):
        if keycode == "KEY_LEFT":
            self._held_left = False
        elif keycode == "KEY_RIGHT":
            self._held_right = False
        elif keycode == "KEY_SPACE":
            self._held_thrust = False

    def stop(self):
        if self.sprites is not None:
            self.sprites.clear()
        self.asteroids = []
        self.bullets = []
        self.ship = None
