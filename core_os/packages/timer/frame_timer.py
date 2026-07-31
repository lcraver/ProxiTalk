"""FrameTimer/FrameTimerManager — mirrors Playdate's playdate.frameTimer:
the same delay/repeat/callback shape as Timer/TimerManager (timer.py), but
counting whole ticks instead of seconds. Useful for logic that needs to be
deterministic against the scheduler's own tick count rather than
wall-clock time -- "wait exactly 10 frames" instead of "wait ~0.5s",
which stays exact regardless of frame-timing jitter (a Timer scheduled
for 0.5s can fire a tick early/late depending on real dt; a FrameTimer
scheduled for 10 frames always fires on exactly the 10th call to tick()).

Same heap-based design as TimerManager (see its docstring for why a flat
list-scan doesn't hold up at scale) -- due times are plain integers here,
so there's no floating-point precision concern to work around at all."""

from __future__ import annotations

import heapq
import itertools
from typing import Callable, List, Optional, Tuple


class FrameTimer:
    def __init__(self, frames: int, on_complete: Optional[Callable[[], None]] = None, repeats: bool = False) -> None:
        self.frames = max(0, frames)
        self.on_complete = on_complete
        self.repeats = repeats
        self.done = False

    def cancel(self) -> None:
        self.done = True


class FrameTimerManager:
    def __init__(self) -> None:
        self._heap: List[Tuple[int, int, FrameTimer]] = []
        self._seq = itertools.count()
        self._frame_count = 0

    def after(self, frames: int, on_complete: Optional[Callable[[], None]] = None, repeats: bool = False) -> FrameTimer:
        timer = FrameTimer(frames, on_complete, repeats)
        self.add(timer)
        return timer

    def add(self, timer: FrameTimer) -> None:
        heapq.heappush(self._heap, (self._frame_count + timer.frames, next(self._seq), timer))

    def tick(self) -> int:
        """Advances by exactly one frame and fires anything now due,
        returning the new frame count."""
        self._frame_count += 1
        while self._heap and self._heap[0][0] <= self._frame_count:
            due, _seq, timer = heapq.heappop(self._heap)
            if timer.done:
                continue
            if timer.on_complete:
                timer.on_complete()
            if timer.repeats:
                # Re-anchor to the CURRENT frame count, not `due + period`
                # -- due can already be stale/behind (e.g. a 0-frame timer
                # whose due was computed before any tick() ever ran), and
                # anchoring to it would let the pushed-back timer stay
                # <= frame_count and refire in this SAME while loop
                # (confirmed: a 0-frame repeating timer fired twice on the
                # very first tick() before this fix). Safe unconditionally
                # here (unlike TimerManager's seconds-based catch-up loop)
                # since tick() only ever advances by exactly one frame at
                # a time -- there's no multi-frame jump that would need
                # `due`-relative catch-up in the first place.
                period = timer.frames if timer.frames > 0 else 1
                heapq.heappush(self._heap, (self._frame_count + period, next(self._seq), timer))
            else:
                timer.done = True
        return self._frame_count
