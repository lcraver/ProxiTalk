#!/usr/bin/env python3
"""
ProxiTalk V2 — Keyboard Matrix Test
Scans the 5x10 key matrix and prints keypresses to console.
Run via SSH: python3 matrix_test.py
Press Ctrl+C to exit.
"""

import RPi.GPIO as GPIO
import time

# ─────────────────────────────────────────
# GPIO PIN ASSIGNMENTS
# Matched to Netlist_Schematic1_2026-06-30.tel (PI1 header, BCM numbering)
# ─────────────────────────────────────────

# Diodes are oriented COL → switch → diode → ROW (anode at COL/switch side,
# cathode at ROW side), so ROW must be driven LOW and COL read with pull-ups
# — the reverse of a typical row-output/col-input matrix.

# Column pins (inputs with pull-ups) — read LOW when key pressed
COLS = [4, 17, 27, 22, 23, 24, 25, 8, 7, 16]   # COL0 → COL9

# Row pins (outputs) — driven LOW one at a time to scan
ROWS = [5, 6, 13, 26, 12]                       # ROW0 → ROW4

# ─────────────────────────────────────────
# KEY MAP
# [row][col] = key label
# Derived from diode nets (Dcr, c=col, r=row) in the netlist
# ─────────────────────────────────────────

KEYMAP = [
    # COL0    COL1     COL2    COL3    COL4      COL5      COL6    COL7     COL8    COL9
    [ 'FN1',  'SHIFT', 'ALT',  '<',    'SPACE1', 'SPACE2', '>',    'CMD',   'CTRL', 'FN2'   ],  # ROW0
    [ 'Z',    'X',     'C',    'V',    'B',      'N',      'M',    'COLON', 'COMMA','ENTER' ],  # ROW1
    [ 'A',    'S',     'D',    'F',    'G',      'H',      'J',    'K',     'L',    'DEL'   ],  # ROW2
    [ 'Q',    'W',     'E',    'R',    'T',      'Y',      'U',    'I',     'O',    'P'     ],  # ROW3
    [ '1',    '2',     '3',    '4',    '5',      '6',      '7',    '8',     '9',    '0'     ],  # ROW4
]

# ─────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────

def setup():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    # Rows = outputs, start HIGH
    for row in ROWS:
        GPIO.setup(row, GPIO.OUT)
        GPIO.output(row, GPIO.HIGH)

    # Columns = inputs with pull-ups enabled
    for col in COLS:
        GPIO.setup(col, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    print("=" * 40)
    print("  ProxiTalk V2 — Matrix Test")
    print("  Press any key to test")
    print("  Ctrl+C to exit")
    print("=" * 40)


# ─────────────────────────────────────────
# SCAN
# ─────────────────────────────────────────

def scan():
    """
    Scan all rows and columns.
    Returns list of (row, col) tuples for any pressed keys.
    """
    pressed = []

    for row_idx, row_pin in enumerate(ROWS):
        # Drive this row LOW
        GPIO.output(row_pin, GPIO.LOW)

        # Small settle delay
        time.sleep(0.001)

        # Read all columns
        for col_idx, col_pin in enumerate(COLS):
            if GPIO.input(col_pin) == GPIO.LOW:
                pressed.append((row_idx, col_idx))

        # Return row HIGH before next scan
        GPIO.output(row_pin, GPIO.HIGH)

    return pressed


# ─────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────

def main():
    setup()

    # Track previously pressed keys to avoid repeat prints
    last_pressed = set()

    try:
        while True:
            pressed = scan()
            pressed_set = set(pressed)

            # New keys pressed since last scan
            new_keys = pressed_set - last_pressed

            for (row, col) in new_keys:
                key = KEYMAP[row][col]
                print(f"KEY PRESSED → {key:10s}  (row={row}, col={col})")

            last_pressed = pressed_set

            # Scan rate — 50Hz is plenty for a keyboard
            time.sleep(0.02)

    except KeyboardInterrupt:
        print("\nExiting matrix test.")

    finally:
        GPIO.cleanup()


if __name__ == "__main__":
    main()
