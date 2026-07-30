"""Real hardware input driver — 5x10 GPIO diode matrix keyboard.

Pin layout and KEYMAP matched to Netlist_Schematic1_2026-06-30.tel (PI1
header, BCM numbering) — carried over from the matrix_test.py/hardware_test.py
bring-up scripts. Diodes are oriented COL -> switch -> diode -> ROW, so rows
are driven LOW one at a time and columns are read with pull-ups (the reverse
of a typical row-output/col-input matrix).

Adds debounce (require N consecutive stable scans before accepting a
transition) and key-repeat (synthetic repeated "down" events while a key is
held), neither of which existed in the original bring-up scripts.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import List, Optional

from core_os.core.drivers.base import KEY_DOWN, KEY_UP, InputDriver, InputEvent

COLS = [4, 17, 27, 22, 23, 24, 25, 8, 7, 16]   # COL0 -> COL9
ROWS = [5, 6, 13, 26, 12]                       # ROW0 -> ROW4

KEYMAP = [
    # COL0    COL1     COL2    COL3    COL4      COL5      COL6    COL7     COL8    COL9
    ['FN1', 'SHIFT', 'ALT', '<', 'SPACE1', 'SPACE2', '>', 'CMD', 'CTRL', 'FN2'],     # ROW0
    ['Z', 'X', 'C', 'V', 'B', 'N', 'M', 'COLON', 'COMMA', 'ENTER'],                  # ROW1
    ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', 'DEL'],                             # ROW2
    ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],                               # ROW3
    ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],                              # ROW4
]

# KEYMAP's raw labels (carried over from the matrix_test.py bring-up script,
# which only ever printed them for debugging) don't match the "KEY_X"
# convention core_os/packages/input/keymap.py and every app/widget's
# onkeydown expects (the Windows emulator path already produces "KEY_X" via
# WIN_TO_LINUX_KEYCODE — see backends/emulator_windows/win_keycodes.py and
# compose.py). Without this translation, real hardware key presses wouldn't
# match anything.
_RAW_TO_KEYCODE = {
    'ENTER': 'KEY_ENTER', 'DEL': 'KEY_BACKSPACE',
    'SHIFT': 'KEY_LEFTSHIFT', 'ALT': 'KEY_LEFTALT', 'CTRL': 'KEY_LEFTCTRL', 'CMD': 'KEY_CMD',
    'FN1': 'KEY_FN1', 'FN2': 'KEY_FN2',
    '<': 'KEY_LEFT', '>': 'KEY_RIGHT',
    'SPACE1': 'KEY_SPACE', 'SPACE2': 'KEY_SPACE',
    'COLON': 'KEY_COLON', 'COMMA': 'KEY_COMMA',
}
for _label in list('ABCDEFGHIJKLMNOPQRSTUVWXYZ'):
    _RAW_TO_KEYCODE[_label] = f'KEY_{_label}'
for _label in list('0123456789'):
    _RAW_TO_KEYCODE[_label] = f'KEY_{_label}'


def _translate_keycode(raw_label: str) -> str:
    return _RAW_TO_KEYCODE.get(raw_label, f'KEY_{raw_label}')


SCAN_HZ = 200.0
DEBOUNCE_STABLE_SCANS = 2
REPEAT_DELAY_S = 0.4
REPEAT_RATE_S = 0.04


class MatrixInputDriver(InputDriver):
    def __init__(self) -> None:
        self._events: deque = deque()
        self._lock = threading.Lock()
        self._running = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._gpio = None

    def start(self) -> None:
        import RPi.GPIO as GPIO

        self._gpio = GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for row in ROWS:
            GPIO.setup(row, GPIO.OUT)
            GPIO.output(row, GPIO.HIGH)
        for col in COLS:
            GPIO.setup(col, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        self._running.set()
        self._thread = threading.Thread(target=self._scan_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running.clear()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self._gpio is not None:
            try:
                self._gpio.cleanup()
            except Exception:
                pass

    def is_ready(self) -> bool:
        return self._running.is_set()

    def poll(self, timeout: float = 0.0) -> List[InputEvent]:
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                if self._events:
                    drained = list(self._events)
                    self._events.clear()
                    return drained
            if time.monotonic() >= deadline:
                return []
            time.sleep(0.002)

    def _scan(self) -> set:
        GPIO = self._gpio
        pressed = set()
        for row_idx, row_pin in enumerate(ROWS):
            GPIO.output(row_pin, GPIO.LOW)
            time.sleep(0.001)
            for col_idx, col_pin in enumerate(COLS):
                if GPIO.input(col_pin) == GPIO.LOW:
                    pressed.add((row_idx, col_idx))
            GPIO.output(row_pin, GPIO.HIGH)
        return pressed

    def _scan_loop(self) -> None:
        scan_interval = 1.0 / SCAN_HZ
        stable_counts: dict = {}
        held: set = set()
        repeat_next_time: dict = {}

        while self._running.is_set():
            raw_pressed = self._scan()

            for key in list(stable_counts.keys()):
                if key not in raw_pressed and key not in held:
                    del stable_counts[key]
            for key in raw_pressed:
                stable_counts[key] = stable_counts.get(key, 0) + 1

            now = time.monotonic()
            for key in raw_pressed:
                row, col = key
                keycode = _translate_keycode(KEYMAP[row][col])
                if key not in held and stable_counts.get(key, 0) >= DEBOUNCE_STABLE_SCANS:
                    held.add(key)
                    repeat_next_time[key] = now + REPEAT_DELAY_S
                    self._push(InputEvent(kind="key", keycode=keycode, keystate=KEY_DOWN, timestamp=now))
                elif key in held and now >= repeat_next_time.get(key, float("inf")):
                    repeat_next_time[key] = now + REPEAT_RATE_S
                    self._push(InputEvent(kind="key", keycode=keycode, keystate=KEY_DOWN, timestamp=now))

            released = held - raw_pressed
            for key in released:
                row, col = key
                keycode = _translate_keycode(KEYMAP[row][col])
                held.discard(key)
                stable_counts.pop(key, None)
                repeat_next_time.pop(key, None)
                self._push(InputEvent(kind="key", keycode=keycode, keystate=KEY_UP, timestamp=now))

            time.sleep(scan_interval)

    def _push(self, event: InputEvent) -> None:
        with self._lock:
            self._events.append(event)
