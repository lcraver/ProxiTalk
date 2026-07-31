"""Timer/TimerManager — mirrors Playdate's playdate.timer, generalizing the
delay/repeating-callback pattern instead of leaving every app to hand-roll
its own time.monotonic() delta-tracking (5 apps did exactly that before
this package existed — see apps/launcher, apps/ui_demo, apps/modifier_hud,
apps/settings, apps/file_browser). Seconds, not Playdate's milliseconds --
every other update(dt) in this codebase (Tween, DoSlide, GifAnimation) is
already in seconds, and mixing units within the same app's update() would
be a constant foot-gun."""

from __future__ import annotations

import heapq
import itertools
import time
from typing import Callable, List, Optional, Tuple


class Timer:
    def __init__(self, duration: float, on_complete: Optional[Callable[[], None]] = None, repeats: bool = False) -> None:
        self.duration = duration
        self.on_complete = on_complete
        self.repeats = repeats
        self.elapsed = 0.0
        # NOT `duration <= 0 and not repeats` -- a zero-duration one-shot
        # timer means "fire on the next tick", not "already done before
        # ever getting a chance to fire". update()'s own duration<=0 branch
        # already fires on_complete correctly the first time it runs; done
        # only needs to become True there, once that's actually happened.
        self.done = False

    def update(self, dt: float) -> None:
        if self.done:
            return
        self.elapsed += dt
        if self.duration <= 0:
            # Degenerate duration: fire once per update() call instead of
            # looping below -- elapsed would never drop below the 0
            # threshold, so the catch-up loop would spin forever.
            if self.repeats:
                self.elapsed = 0.0
            else:
                self.done = True
            if self.on_complete:
                self.on_complete()
            return
        # A while loop (not `if`) so a dt spanning multiple full periods
        # (e.g. after a long pause) fires a repeating timer once per period
        # it actually crossed, rather than desyncing to "one firing, then
        # wait a full period again" no matter how far dt overshot.
        while self.elapsed >= self.duration and not self.done:
            if self.repeats:
                self.elapsed -= self.duration
            else:
                self.elapsed = self.duration
                self.done = True
            if self.on_complete:
                self.on_complete()

    def cancel(self) -> None:
        self.done = True


class TimerManager:
    """Drives every registered Timer off a single min-heap of absolute due
    times (relative to this manager's own running `_elapsed_total` clock),
    not a flat list scanned/re-filtered every tick -- the earlier list-scan
    design cost O(n) per tick regardless of how many timers were anywhere
    close to firing, which is fine for the handful of timers a typical app
    has in flight but falls over at real scale: scheduling a MIDI file's
    worth of notes (~106k one-shot timers for a dense real-world file)
    measured at 31ms for a SINGLE tick's scan -- 62% of an entire 20Hz
    frame budget spent on bookkeeping before any timer even fires. A heap
    only ever touches the timers actually due this tick (O(log n) per
    schedule/fire, not O(n) per tick regardless of what's due), which is
    the actual fix.

    Timer objects themselves are untouched and still usable completely
    standalone (own dt-based .update()) -- this manager only uses them as
    plain (duration, on_complete, repeats, done) data holders and drives
    firing itself, bypassing Timer.update() entirely, since tracking due
    times centrally is what makes the heap approach work."""

    def __init__(self) -> None:
        self._heap: List[Tuple[float, int, Timer]] = []
        self._seq = itertools.count()
        self._elapsed_total = 0.0
        self._last_time: Optional[float] = None

    def after(self, duration: float, on_complete: Optional[Callable[[], None]] = None, repeats: bool = False) -> Timer:
        timer = Timer(duration, on_complete, repeats)
        self.add(timer)
        return timer

    def add(self, timer: Timer) -> None:
        heapq.heappush(self._heap, (self._elapsed_total + timer.duration, next(self._seq), timer))

    def update(self, dt: float) -> None:
        self._elapsed_total += dt
        # `_elapsed_total` is a running sum of every dt this manager has
        # ever seen, never reset -- unlike Timer's own per-timer `elapsed`
        # (subtracted back toward 0 on every firing, which keeps its
        # float error bounded to one period), so it accumulates the usual
        # binary-float rounding noise over many additions. A due time
        # computed earlier (e.g. via repeated `due + duration` for a
        # repeating timer) can end up a handful of ULPs ahead of
        # `_elapsed_total` even though mathematically they should be
        # exactly equal (confirmed: ten additions of 0.1 land on
        # 0.9999999999999999, not 1.0) -- a tiny epsilon absorbs that
        # without meaningfully affecting real timing (dt from wall-clock
        # ticks is many orders of magnitude coarser than this).
        while self._heap and self._heap[0][0] <= self._elapsed_total + 1e-9:
            due, _seq, timer = heapq.heappop(self._heap)
            if timer.done:
                continue  # cancelled before it got here -- lazy deletion, just drop it
            if timer.on_complete:
                timer.on_complete()
            if timer.repeats:
                # Degenerate (<=0) duration: push far enough ahead that
                # THIS while loop doesn't immediately re-pop it (which
                # would spin forever) -- defers to the next update() call
                # instead, i.e. fires once per tick, matching a plain
                # delay=0 repeating timer's only sane interpretation. Must
                # clear the comparison's own 1e-9 tolerance above by a
                # comfortable margin, or push == compare-threshold exactly
                # and it re-fires immediately anyway (this hung the first
                # version of this fix).
                next_due = due + timer.duration if timer.duration > 0 else self._elapsed_total + 1e-3
                heapq.heappush(self._heap, (next_due, next(self._seq), timer))
            else:
                timer.done = True

    def tick(self) -> float:
        """Computes dt from wall-clock time itself and advances every
        registered timer with it, returning that same dt -- so an app's
        update() becomes `dt = self.timers.tick()` instead of hand-rolling
        its own _last_update_time/time.monotonic() block, and the returned
        dt still feeds any Tweens the app is separately driving."""
        now = time.monotonic()
        dt = 0.0 if self._last_time is None else now - self._last_time
        self._last_time = now
        self.update(dt)
        return dt
