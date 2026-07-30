#!/usr/bin/env python3
"""
ProxiTalk V2 — Keyboard Matrix Diagnostic
Deeper diagnosis for false-positive / missed keypresses than matrix_test.py's
plain scan-and-print. Run via SSH: python3 matrix_diagnostic.py
"""

import os
import sys
import threading
import time

import RPi.GPIO as GPIO

# ─────────────────────────────────────────
# GPIO PIN ASSIGNMENTS (same as matrix_test.py)
# ─────────────────────────────────────────

COLS = [4, 17, 27, 22, 23, 24, 25, 8, 7, 16]   # COL0 → COL9
ROWS = [5, 6, 13, 26, 12]                       # ROW0 → ROW4

# GPIO7/GPIO8 double as SPI0 CE1/CE0 (chip-select). If SPI is enabled
# (dtparam=spi=on) and anything opens spidev0.x — e.g. the LED test in
# hardware_test.py — the kernel drives these as chip-select, fighting the
# matrix code's attempt to read them as plain inputs. Flag them by name
# whenever they show up stuck so the SPI conflict is obvious, not just a
# pin number.
SPI_CONFLICT_PINS = {8: 'SPI0 CE0', 7: 'SPI0 CE1'}

KEYMAP = [
    [ 'FN1',  'SHIFT', 'ALT',  '<',    'SPACE1', 'SPACE2', '>',    'CMD',   'CTRL', 'FN2'   ],
    [ 'Z',    'X',     'C',    'V',    'B',      'N',      'M',    'COLON', 'COMMA','ENTER' ],
    [ 'A',    'S',     'D',    'F',    'G',      'H',      'J',    'K',     'L',    'DEL'   ],
    [ 'Q',    'W',     'E',    'R',    'T',      'Y',      'U',    'I',     'O',    'P'     ],
    [ '1',    '2',     '3',    '4',    '5',      '6',      '7',    '8',     '9',    '0'     ],
]


def matrix_setup():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for row in ROWS:
        GPIO.setup(row, GPIO.OUT)
        GPIO.output(row, GPIO.HIGH)
    for col in COLS:
        GPIO.setup(col, GPIO.IN, pull_up_down=GPIO.PUD_UP)


def matrix_scan(settle=0.001):
    """One full row/col sweep. Returns [(row, col), ...] currently reading LOW."""
    pressed = []
    for row_idx, row_pin in enumerate(ROWS):
        GPIO.output(row_pin, GPIO.LOW)
        time.sleep(settle)
        for col_idx, col_pin in enumerate(COLS):
            if GPIO.input(col_pin) == GPIO.LOW:
                pressed.append((row_idx, col_idx))
        GPIO.output(row_pin, GPIO.HIGH)
    return pressed


def _col_note(col_idx):
    pin = COLS[col_idx]
    return f"  <-- {SPI_CONFLICT_PINS[pin]} (GPIO{pin}) — SPI conflict?" if pin in SPI_CONFLICT_PINS else ""


# ─────────────────────────────────────────
# TEST 1 — Idle stuck-pin / false-positive check
# Baseline: rows all HIGH (idle), no key touched. Any column reading LOW
# is either a stuck/shorted line or an SPI/peripheral conflict — not a
# real keypress. Also runs a live full-matrix idle scan since a bad row
# driver can cause the same symptom only while its row is active.
# ─────────────────────────────────────────

def stuck_pin_test():
    matrix_setup()
    print("=" * 50)
    print("  Idle Stuck-Pin Test")
    print("  Do NOT touch the keyboard. Checking baseline...")
    print("=" * 50)

    # Rows all HIGH, no row selected — every column must read HIGH.
    bad_baseline = [c for c, pin in enumerate(COLS) if GPIO.input(pin) == GPIO.LOW]
    if bad_baseline:
        print("\n[CRITICAL] Columns reading LOW with ALL rows idle HIGH")
        print("  (impossible during a real scan — wiring short, dead pull-up,")
        print("  or a peripheral driving the pin):")
        for c in bad_baseline:
            print(f"    COL{c} (GPIO{COLS[c]}){_col_note(c)}")
    else:
        print("\n  Idle baseline clean — no column stuck LOW at rest.")

    print(f"\n  Running {200} scans (~4s) with all rows cycled, still don't touch it...")
    counts = {}
    for _ in range(200):
        for (r, c) in matrix_scan():
            counts[(r, c)] = counts.get((r, c), 0) + 1
        time.sleep(0.02)

    if not counts:
        print("\n  RESULT: clean. No false positives across 200 scans.")
    else:
        print(f"\n  RESULT: {len(counts)} key(s) fired with nothing pressed:")
        for (r, c), n in sorted(counts.items(), key=lambda kv: -kv[1]):
            pct = 100 * n / 200
            print(f"    {KEYMAP[r][c]:8s} (row={r}, col={c})  {n}/200 scans ({pct:.0f}%){_col_note(c)}")
        rows_per_col = {}
        for (r, c) in counts:
            rows_per_col.setdefault(c, set()).add(r)
        stuck_cols = [c for c, rs in rows_per_col.items() if len(rs) == len(ROWS)]
        if stuck_cols:
            print("\n  Pattern: same column(s) fire on EVERY row → that column line")
            print("  itself is stuck/contended, not a real key. Check wiring/solder")
            print("  on that column, and check for SPI/peripheral pin conflicts above:")
            for c in stuck_cols:
                print(f"    COL{c} (GPIO{COLS[c]}){_col_note(c)}")

    GPIO.cleanup()


# ─────────────────────────────────────────
# TEST 2 — Live raw view (undebounced, redraws in place)
# ─────────────────────────────────────────

def live_raw_view():
    matrix_setup()
    print("=" * 50)
    print("  Live Raw Matrix View — Ctrl+C to exit")
    print("  '#' = reading LOW (pressed) right now, '.' = HIGH")
    print("=" * 50)
    start = time.time()
    scan_count = 0
    spinner = "|/-\\"
    try:
        while True:
            pressed = set(matrix_scan())
            scan_count += 1
            elapsed = time.time() - start
            lines = [f"  scan #{scan_count}  t={elapsed:6.1f}s  {spinner[scan_count % 4]}   (frame changes only when a reading changes)"]
            lines.append("      " + "".join(f"C{c%10}".ljust(4) for c in range(len(COLS))))
            for r in range(len(ROWS)):
                row_cells = "".join(
                    ("#".ljust(4) if (r, c) in pressed else ".".ljust(4))
                    for c in range(len(COLS))
                )
                lines.append(f"ROW{r}  {row_cells}")
            sys.stdout.write("\033[H\033[J")
            sys.stdout.write("\n".join(lines) + "\n")
            sys.stdout.flush()
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nExiting live view.")
    finally:
        GPIO.cleanup()


# ─────────────────────────────────────────
# TEST 3 — Per-key bounce / missed-input test
# Isolates one switch at a time: holds its row LOW and tight-samples its
# column for a window, recording every raw edge. 0 edges = key never
# registered (the "not properly detecting input" symptom). >2 edges =
# contact bounce (or a flaky connection re-triggering).
# ─────────────────────────────────────────

def bounce_test():
    matrix_setup()
    print("=" * 50)
    print("  Per-Key Bounce / Missed-Input Test")
    print("  Press and release each key ONCE when prompted.")
    print("  Ctrl+C to stop early.")
    print("=" * 50)

    flat_keys = [(r, c, KEYMAP[r][c]) for r in range(len(ROWS)) for c in range(len(COLS))]
    results = []

    try:
        for (r, c, label) in flat_keys:
            row_pin = ROWS[r]
            col_pin = COLS[c]
            print(f"\n  Press '{label}' (row={r}, col={c})... ", end="", flush=True)

            GPIO.output(row_pin, GPIO.LOW)
            edges = []
            last_state = GPIO.input(col_pin)
            start = time.time()
            timeout = 5.0
            # Sample as fast as Python allows for a tight bounce window.
            while time.time() - start < timeout:
                state = GPIO.input(col_pin)
                if state != last_state:
                    edges.append(time.time() - start)
                    last_state = state
                if len(edges) >= 1 and state == GPIO.HIGH and (time.time() - start) - edges[-1] > 0.15:
                    # Back HIGH and stayed there — key released, done early.
                    break
            GPIO.output(row_pin, GPIO.HIGH)

            if not edges:
                print("NOT DETECTED (timed out)")
                results.append((label, r, c, "MISSED", 0, 0.0))
            else:
                bounce_count = max(0, len(edges) - 2)
                duration = edges[-1] - edges[0]
                if bounce_count == 0:
                    print(f"OK (clean, {duration*1000:.1f}ms)")
                    results.append((label, r, c, "OK", 0, duration))
                else:
                    print(f"BOUNCY ({bounce_count} extra edges over {duration*1000:.1f}ms)")
                    results.append((label, r, c, "BOUNCY", bounce_count, duration))
    except KeyboardInterrupt:
        print("\n\nStopped early.")
    finally:
        GPIO.cleanup()

    print("\n" + "=" * 50)
    print("  Summary")
    print("=" * 50)
    missed = [x for x in results if x[3] == "MISSED"]
    bouncy = [x for x in results if x[3] == "BOUNCY"]
    if missed:
        print(f"  MISSED ({len(missed)}): " + ", ".join(x[0] for x in missed))
    if bouncy:
        print(f"  BOUNCY ({len(bouncy)}):")
        for (label, r, c, _, bc, dur) in sorted(bouncy, key=lambda x: -x[4]):
            print(f"    {label:8s} (row={r}, col={c})  {bc} extra edges, {dur*1000:.1f}ms{_col_note(c)}")
    if not missed and not bouncy:
        print("  All tested keys clean.")


# ─────────────────────────────────────────
# TEST 4 — Ghosting / rollover check
# With this board's diode orientation, a real n-key-rollover ghost shows
# up as a 3rd "phantom" cell completing the rectangle of two genuinely
# pressed keys that share neither row nor column.
# ─────────────────────────────────────────

def ghost_test():
    matrix_setup()
    print("=" * 50)
    print("  Ghosting / Rollover Test")
    print("  Try pressing 2-3 keys at once in different rows/cols.")
    print("  Ctrl+C to exit.")
    print("=" * 50)
    last = set()
    try:
        while True:
            pressed = set(matrix_scan())
            if pressed != last and pressed:
                labels = [f"{KEYMAP[r][c]}(r{r}c{c})" for (r, c) in pressed]
                print(f"\n  Pressed: {', '.join(labels)}")
                if len(pressed) >= 3:
                    rows = {r for r, c in pressed}
                    cols = {c for r, c in pressed}
                    if len(rows) * len(cols) == len(pressed) and len(pressed) == len(rows) * len(cols):
                        print("  >>> Rectangle pattern detected — classic ghost combo.")
                        print("      If you only physically pressed 2 of these, the 3rd")
                        print("      is a phantom key (diode/wiring issue on that pair).")
            last = pressed
            time.sleep(0.02)
    except KeyboardInterrupt:
        print("\nExiting ghost test.")
    finally:
        GPIO.cleanup()


# ─────────────────────────────────────────
# TEST 5 — Settle-time sweep
# Too-short a delay between driving a row LOW and reading columns can
# read before the line has settled (pull-up RC, cable capacitance),
# producing false positives that look random. Sweeps the delay and
# counts idle false reads at each value.
# ─────────────────────────────────────────

def timing_sweep():
    matrix_setup()
    print("=" * 50)
    print("  Settle-Time Sweep")
    print("  Do NOT touch the keyboard during this test.")
    print("=" * 50)

    delays_ms = [0, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0]
    scans_per_delay = 100
    total_cells = scans_per_delay * len(ROWS) * len(COLS)

    for d_ms in delays_ms:
        d = d_ms / 1000.0
        false_count = 0
        for _ in range(scans_per_delay):
            false_count += len(matrix_scan(settle=d))
        pct = 100 * false_count / total_cells
        print(f"  settle={d_ms:5.1f}ms   false reads: {false_count:5d}/{total_cells}  ({pct:.2f}%)")

    GPIO.cleanup()
    print("\n  If false reads drop sharply once delay increases, current")
    print("  matrix_test.py settle (1ms) may be too short for this board's")
    print("  wiring/capacitance — bump time.sleep(0.001) in the scan loop.")


# ─────────────────────────────────────────
# TEST 6 — All-rows-low column probe (bypasses row scanning)
# Drives every row LOW at once instead of cycling them, then watches one
# column raw. This removes "did the scan pick the right row" as a
# variable entirely: if a real keypress still never pulls the column
# LOW, that switch/diode/trace is genuinely open — not a scan-timing or
# row-mapping bug.
# ─────────────────────────────────────────

def column_probe():
    print("=" * 50)
    print("  All-Rows-Low Column Probe")
    print("  Bypasses row scanning — drives every row LOW at once so any")
    print("  key press on the chosen column, in any row, should pull it LOW.")
    print("=" * 50)
    try:
        raw = input(f"  Column index to probe (0-{len(COLS)-1}): ").strip()
        col_idx = int(raw)
        if not (0 <= col_idx < len(COLS)):
            raise ValueError
    except (ValueError, EOFError, KeyboardInterrupt):
        print("  Invalid column index, aborting.")
        return

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for row in ROWS:
        GPIO.setup(row, GPIO.OUT)
        GPIO.output(row, GPIO.LOW)   # all rows LOW simultaneously
    col_pin = COLS[col_idx]
    GPIO.setup(col_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    print(f"\n  Watching COL{col_idx} (GPIO{col_pin}){_col_note(col_idx)}")
    print("  Press ANY key in this column (any row). Ctrl+C to stop.\n")

    last = GPIO.input(col_pin)
    print(f"  t=0.0s  baseline: {'LOW (already stuck!)' if last == GPIO.LOW else 'HIGH (idle, correct)'}")
    start = time.time()
    try:
        while True:
            state = GPIO.input(col_pin)
            if state != last:
                label = "LOW (pulled down — press registered)" if state == GPIO.LOW else "HIGH (released)"
                print(f"  t={time.time()-start:6.1f}s  {label}")
                last = state
            time.sleep(0.005)
    except KeyboardInterrupt:
        print("\nExiting column probe.")
    finally:
        GPIO.cleanup()


# ─────────────────────────────────────────
# TEST 7 — Interactive remap wizard
# If detected (row, col) doesn't match KEYMAP's assumption for a key you
# know you pressed, the table itself is wrong for this board (netlist
# mismatch, or a reversed/shifted ribbon connector) — not a scan bug.
# This builds the TRUE row/col -> label mapping from what you actually
# press, instead of trusting KEYMAP.
# ─────────────────────────────────────────

def remap_wizard():
    matrix_setup()
    print("=" * 50)
    print("  Interactive Remap Wizard")
    print("  Checking for stuck cells first — don't touch the keyboard...")
    print("=" * 50)

    # Auto-detect stuck-always-pressed cells (e.g. the SPI-conflicted cols)
    # so they don't get grabbed as "new presses" and hang the wizard
    # waiting for a release that never comes.
    stuck_counts = {}
    for _ in range(20):
        for cell in matrix_scan():
            stuck_counts[cell] = stuck_counts.get(cell, 0) + 1
        time.sleep(0.02)
    ignored = {cell for cell, n in stuck_counts.items() if n == 20}
    if ignored:
        print(f"  Ignoring {len(ignored)} stuck cell(s) for this session:")
        for (r, c) in sorted(ignored):
            print(f"    row={r} col={c}{_col_note(c)}")
    else:
        print("  No stuck cells detected.")

    print("\n  Press one key at a time, then type what it was when asked.")
    print("  Ctrl+C when done to print the corrected table.")
    print("=" * 50)

    learned = {}  # (row, col) -> label
    last_pressed = set(ignored)
    try:
        while True:
            pressed = set(matrix_scan()) - ignored
            new_keys = pressed - last_pressed
            if new_keys:
                r, c = sorted(new_keys)[0]  # take one even if several land at once
                old_label = KEYMAP[r][c]
                try:
                    label = input(
                        f"\n  Detected row={r} col={c} (KEYMAP currently says '{old_label}')."
                        f" What key did you press? "
                    ).strip()
                except (EOFError, KeyboardInterrupt):
                    raise KeyboardInterrupt
                if label:
                    if (r, c) in learned and learned[(r, c)] != label.upper():
                        print(f"  Note: row={r} col={c} was already learned as "
                              f"'{learned[(r, c)]}', now overwritten with '{label.upper()}'.")
                    learned[(r, c)] = label.upper()
                    if label.upper() != old_label:
                        print(f"  MISMATCH confirmed: row={r} col={c} is really "
                              f"'{label.upper()}', not '{old_label}'.")
                # Wait for release before watching for the next new press.
                while set(matrix_scan()) & {(r, c)}:
                    time.sleep(0.02)
                last_pressed = set()
                continue
            last_pressed = pressed
            time.sleep(0.02)
    except KeyboardInterrupt:
        print("\n\nExiting remap wizard.")
    finally:
        GPIO.cleanup()

    if not learned:
        print("  Nothing learned.")
        return

    print("\n" + "=" * 50)
    print("  Learned mapping vs current KEYMAP")
    print("=" * 50)
    mismatches = 0
    for (r, c), label in sorted(learned.items()):
        current = KEYMAP[r][c]
        flag = "" if label == current else "  <-- MISMATCH"
        if flag:
            mismatches += 1
        print(f"  row={r} col={c}: learned='{label}'  keymap='{current}'{flag}")

    print(f"\n  {mismatches} mismatch(es) out of {len(learned)} learned key(s).")
    print("\n  Corrected rows for KEYMAP (paste over the matching rows,")
    print("  '?' means not yet learned for that cell):")
    for r in range(len(ROWS)):
        row_vals = [learned.get((r, c), '?') for c in range(len(COLS))]
        formatted = ", ".join(f"'{v}'" for v in row_vals)
        print(f"    [ {formatted} ],  # ROW{r}")


# ─────────────────────────────────────────
# TEST 8 — SPI conflict tester
# GPIO8/GPIO7 (COL7/COL8) double as SPI0 CE0/CE1. This proves the
# conflict live instead of just theorizing: it opens each spidev device
# and holds chip-select LOW for a couple seconds with a slow, oversized
# transfer, while a background thread watches the same pin via plain
# RPi.GPIO. If the pin dips LOW exactly while SPI is transferring, the
# kernel SPI driver — not a keypress — is what's driving it.
# ─────────────────────────────────────────

CONFIG_TXT_PATHS = ["/boot/firmware/config.txt", "/boot/config.txt"]
SPI_CE_PINS = [
    ("/dev/spidev0.0", 0, 0, 8, "GPIO8 / COL7 (SPI0 CE0)"),
    ("/dev/spidev0.1", 0, 1, 7, "GPIO7 / COL8 (SPI0 CE1)"),
]


def _watch_pin_for_low(pin, duration, result):
    end = time.time() + duration
    seen_low = False
    while time.time() < end:
        if GPIO.input(pin) == GPIO.LOW:
            seen_low = True
        time.sleep(0.0005)
    result.append(seen_low)


def spi_conflict_test():
    print("=" * 50)
    print("  SPI Conflict Tester")
    print("=" * 50)

    spi_nodes = [p for p, *_ in SPI_CE_PINS if os.path.exists(p)]
    if spi_nodes:
        print(f"  SPI device nodes present: {', '.join(spi_nodes)}")
    else:
        print("  No /dev/spidev* nodes present — SPI not active at the kernel")
        print("  level right now. Skipping live test (nothing to conflict with).")

    for path in CONFIG_TXT_PATHS:
        if os.path.isfile(path):
            try:
                with open(path) as f:
                    spi_lines = [l.strip() for l in f if "spi" in l.lower() and not l.strip().startswith("#")]
                print(f"\n  {path}:")
                if spi_lines:
                    for l in spi_lines:
                        print(f"    {l}")
                else:
                    print("    (no active spi lines found)")
            except OSError as e:
                print(f"  Couldn't read {path}: {e}")
            break

    if not spi_nodes:
        return

    try:
        import spidev
    except ImportError:
        print("\n  spidev module not installed — can't run the live causal test.")
        print("  (SPI device nodes exist, so the conflict theory still stands —")
        print("  just can't prove it live from here.)")
        return

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for _, _, _, pin, label in SPI_CE_PINS:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        print(f"\n  Baseline {label}: {'LOW (already stuck)' if GPIO.input(pin) == GPIO.LOW else 'HIGH (idle)'}")

    for dev_path, bus, device, pin, label in SPI_CE_PINS:
        if not os.path.exists(dev_path):
            print(f"\n  {dev_path} not present, skipping {label}.")
            continue
        print(f"\n  Testing {label} — holding SPI transfer open ~2.5s...")
        result = []
        watcher = threading.Thread(target=_watch_pin_for_low, args=(pin, 2.5, result))
        watcher.start()
        spi = spidev.SpiDev()
        try:
            spi.open(bus, device)
            spi.max_speed_hz = 5000  # slow on purpose — stretches the CE-low window so the watcher can catch it
            spi.mode = 0
            spi.xfer2([0x00] * 1024)
        except Exception as e:
            print(f"    Error during SPI transfer: {e}")
        finally:
            spi.close()
        watcher.join()

        if result and result[0]:
            print(f"    CONFIRMED: {label} went LOW during the SPI transfer.")
            print(f"    The kernel SPI driver drives this pin as chip-select —")
            print(f"    that's a real conflict with using it as a matrix column input.")
        else:
            print(f"    {label} stayed HIGH throughout this transfer — no conflict")
            print(f"    caught this time (try again, or it may only trigger while")
            print(f"    something else actively uses this specific spidev device).")

    GPIO.cleanup()
    print("\n  Fix if confirmed: stop using SPI0 (disable dtparam=spi=on and any")
    print("  code opening spidev0.x, e.g. the LED test), or move COL7/COL8 off")
    print("  GPIO8/GPIO7 onto unused GPIO pins.")


# ─────────────────────────────────────────
# MENU
# ─────────────────────────────────────────

def main():
    print("=" * 50)
    print("  ProxiTalk V2 — Matrix Diagnostic")
    print("=" * 50)
    print("  [1] Idle stuck-pin / false-positive check  (start here)")
    print("  [2] Live raw matrix view")
    print("  [3] Per-key bounce / missed-input test")
    print("  [4] Ghosting / rollover check")
    print("  [5] Settle-time sweep")
    print("  [6] All-rows-low column probe (isolate dead columns)")
    print("  [7] Interactive remap wizard (find true row/col per key)")
    print("  [8] SPI conflict tester (col7/col8)")
    print("  [q] Quit")
    print("=" * 50)

    while True:
        try:
            choice = input("Choice: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if choice == "1":
            stuck_pin_test()
        elif choice == "2":
            live_raw_view()
        elif choice == "3":
            bounce_test()
        elif choice == "4":
            ghost_test()
        elif choice == "5":
            timing_sweep()
        elif choice == "6":
            column_probe()
        elif choice == "7":
            remap_wizard()
        elif choice == "8":
            spi_conflict_test()
        elif choice == "q":
            return
        else:
            print("Enter 1-5 or q.")


if __name__ == "__main__":
    main()
