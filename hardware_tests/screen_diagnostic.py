#!/usr/bin/env python3
"""
ProxiTalk V2 — Screen (SSD1309, I2C) Diagnostic
Deeper diagnosis for a dead/blank display than hardware_test.py's screen_test().
Run via SSH: python3 screen_diagnostic.py
"""

import os
import subprocess
import time

# ─────────────────────────────────────────
# CONFIG (same as hardware_test.py)
# ─────────────────────────────────────────

DISPLAY_WIDTH = 128
DISPLAY_HEIGHT = 64
I2C_PORT = 1
I2C_ADDRESS = 0x3C          # SSD1309 boards are usually 0x3C or 0x3D
CANDIDATE_ADDRESSES = [0x3C, 0x3D]

CONFIG_TXT_PATHS = ["/boot/firmware/config.txt", "/boot/config.txt"]


# ─────────────────────────────────────────
# TEST 0 — Raw SDA/SCL pin level check
# i2cdetect hanging on the whole bus (not just one address) means SDA or
# SCL is stuck LOW at the hardware level. This reads GPIO2 (SDA1) and
# GPIO3 (SCL1) directly, bypassing the I2C subsystem entirely, so a
# stuck line shows up even though the kernel driver can't get a word in.
# Physical pin3 = SDA, pin5 = SCL. Note: pin5's header neighbor is pin7
# (GPIO4 / matrix COL0) and pin6 is GND — worth a continuity check
# against both if this comes back stuck.
# ─────────────────────────────────────────

def raw_i2c_pin_check():
    print("=" * 50)
    print("  Raw SDA/SCL Pin Level Check")
    print("=" * 50)
    try:
        import RPi.GPIO as GPIO
    except ImportError as e:
        print(f"  RPi.GPIO not installed: {e}")
        return

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for pin, name in [(2, "SDA1 (GPIO2, physical pin3)"), (3, "SCL1 (GPIO3, physical pin5)")]:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        level = GPIO.input(pin)
        status = "LOW — stuck! (should idle HIGH)" if level == GPIO.LOW else "HIGH (correct idle state)"
        print(f"  {name}: {status}")
    GPIO.cleanup()

    print("\n  If either read LOW: that line is being held down by something")
    print("  (short to GND, a latched device, or a solder bridge to a")
    print("  neighboring pin) and no I2C traffic can happen until it's freed.")
    print("  A stuck SDA can sometimes be freed by power-cycling the whole")
    print("  Pi + display (not just a reboot) so any latched device resets.")


# ─────────────────────────────────────────
# TEST 1 — I2C bus scan
# Confirms wiring/address before touching the luma driver at all. If
# nothing shows up here, it's SDA/SCL/VCC/GND/address — not software.
# ─────────────────────────────────────────

def i2c_bus_scan():
    print("=" * 50)
    print("  I2C Bus Scan")
    print("=" * 50)

    dev_path = f"/dev/i2c-{I2C_PORT}"
    if os.path.exists(dev_path):
        print(f"  {dev_path} present — I2C interface is enabled.")
    else:
        print(f"  {dev_path} NOT FOUND — I2C isn't enabled at the kernel level.")
        for path in CONFIG_TXT_PATHS:
            if os.path.isfile(path):
                try:
                    with open(path) as f:
                        i2c_lines = [l.strip() for l in f if "i2c" in l.lower() and not l.strip().startswith("#")]
                    print(f"\n  {path}:")
                    print("\n".join(f"    {l}" for l in i2c_lines) if i2c_lines else "    (no active i2c lines)")
                except OSError as e:
                    print(f"  Couldn't read {path}: {e}")
                break
        print("\n  Fix: add 'dtparam=i2c_arm=on' to config.txt (or `sudo raspi-config`")
        print("  -> Interface Options -> I2C -> enable), then reboot.")
        return

    try:
        result = subprocess.run(["i2cdetect", "-y", str(I2C_PORT)], capture_output=True, text=True, timeout=10)
    except FileNotFoundError:
        print("\n  `i2cdetect` not installed. Install with: sudo apt install i2c-tools")
        return
    except subprocess.TimeoutExpired:
        print("\n  i2cdetect timed out — bus may be stuck/held low by a device.")
        return

    print()
    print(result.stdout)

    found = []
    for addr in CANDIDATE_ADDRESSES:
        hexpair = f"{addr:02x}"
        if hexpair in result.stdout.lower():
            found.append(addr)

    if found:
        print(f"  Device responding at: {', '.join(hex(a) for a in found)}")
        if I2C_ADDRESS not in found:
            print(f"  NOTE: code expects {hex(I2C_ADDRESS)} but device answered at "
                  f"{', '.join(hex(a) for a in found)} instead — update I2C_ADDRESS "
                  f"in hardware_test.py.")
    else:
        print("  NOTHING responded on the bus.")
        print("  Not a software problem at this point — check:")
        print("    - SDA/SCL wires (and that they aren't swapped)")
        print("    - VCC/GND to the display")
        print("    - Solder joints on the display's I2C pins")
        print("    - Try the other common address (0x3C vs 0x3D) if board has a jumper")


# ─────────────────────────────────────────
# TEST 2 — Raw luma init test
# Isolates driver-level failures (wrong device class, bad geometry, etc.)
# from wiring failures — prints the full exception instead of hardware_test.py's
# swallowed "Screen not detected" message.
# ─────────────────────────────────────────

def raw_init_test(address=None):
    print("=" * 50)
    print("  Raw Driver Init Test")
    print("=" * 50)

    try:
        from luma.core.interface.serial import i2c
        from luma.oled.device import ssd1309
    except ImportError as e:
        print(f"  luma modules not installed: {e}")
        print("  pip3 install luma.oled")
        return None

    addresses = [address] if address else CANDIDATE_ADDRESSES
    for addr in addresses:
        print(f"\n  Trying address {hex(addr)}...")
        try:
            serial = i2c(port=I2C_PORT, address=addr)
            device = ssd1309(serial)
            print(f"  SUCCESS — device initialized at {hex(addr)}.")
            print(f"  Reported size: {device.width}x{device.height}")
            return device
        except Exception as e:
            print(f"  FAILED at {hex(addr)}: {type(e).__name__}: {e}")

    print("\n  Init failed at every candidate address.")
    return None


# ─────────────────────────────────────────
# TEST 3 — Guided visual test
# Shows one pattern at a time and asks you to confirm what you saw, so a
# "connects but shows nothing" failure (power/contrast) is distinguished
# from "shows garbage" (wrong controller/geometry) or "shows nothing at
# all" (wiring).
# ─────────────────────────────────────────

def _pattern_full(img, draw, on):
    draw.rectangle([(0, 0), (img.width - 1, img.height - 1)], fill=255 if on else 0)


def _pattern_border(img, draw):
    draw.rectangle([(0, 0), (img.width - 1, img.height - 1)], outline=255, fill=0)


def _pattern_checkerboard(img, draw, size=8):
    for y in range(0, img.height, size):
        for x in range(0, img.width, size):
            if ((x // size) + (y // size)) % 2 == 0:
                draw.rectangle([(x, y), (x + size - 1, y + size - 1)], fill=255)


def _pattern_corner_pixels(img, draw):
    w, h = img.width - 1, img.height - 1
    for (x, y) in [(0, 0), (w, 0), (0, h), (w, h)]:
        draw.point((x, y), fill=255)
        draw.rectangle([(max(0, x - 2), max(0, y - 2)), (min(w, x + 2), min(h, y + 2))], outline=255)


def _pattern_text(img, draw):
    draw.text((4, 4), "TEST 12345", fill=255)
    draw.text((4, 20), "abcXYZ", fill=255)


def guided_visual_test(device):
    from PIL import Image, ImageDraw

    print("=" * 50)
    print("  Guided Visual Test")
    print("  Answer y/n for what you actually see on the physical screen.")
    print("=" * 50)

    patterns = [
        ("Full WHITE screen", lambda img, draw: _pattern_full(img, draw, True)),
        ("Full BLACK (blank) screen", lambda img, draw: _pattern_full(img, draw, False)),
        ("White border/outline only", _pattern_border),
        ("Checkerboard", _pattern_checkerboard),
        ("Small marks in all 4 corners", _pattern_corner_pixels),
        ("Text 'TEST 12345 / abcXYZ'", _pattern_text),
    ]

    results = []
    for label, draw_fn in patterns:
        img = Image.new("1", (device.width, device.height), 0)
        draw = ImageDraw.Draw(img)
        draw_fn(img, draw)
        try:
            device.display(img)
        except Exception as e:
            print(f"\n  [{label}] display() raised: {type(e).__name__}: {e}")
            results.append((label, "ERROR"))
            continue

        try:
            ans = input(f"\n  Showing: {label}. Did you see it correctly? (y/n) ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  Stopped early.")
            break
        results.append((label, "OK" if ans.startswith("y") else "FAIL"))

    blank = Image.new("1", (device.width, device.height), 0)
    try:
        device.display(blank)
    except Exception:
        pass

    print("\n" + "=" * 50)
    print("  Summary")
    print("=" * 50)
    for label, outcome in results:
        print(f"  [{outcome:5s}] {label}")

    fails = [r for r in results if r[1] != "OK"]
    if not fails:
        print("\n  All patterns confirmed visible — screen and driver are fine.")
    elif all(r[1] != "OK" for r in results):
        print("\n  NOTHING visible at all despite the driver initializing without")
        print("  error — check contrast (test 4), power to the panel, or a bad")
        print("  ribbon/solder connection between the controller and the glass.")
    else:
        print("\n  Partial failure — note which specific patterns failed above;")
        print("  garbled/partial output usually means wrong width/height or a")
        print("  flaky connection rather than a fully dead panel.")


# ─────────────────────────────────────────
# TEST 4 — Contrast sweep
# Some SSD1309 clones default to very low contrast — driver initializes
# fine and display() succeeds, but the panel looks "off" at normal
# contrast. Sweeps contrast levels with a static pattern shown at each.
# ─────────────────────────────────────────

def contrast_sweep(device):
    from PIL import Image, ImageDraw

    print("=" * 50)
    print("  Contrast Sweep")
    print("  Watch the screen while this runs — note the lowest level")
    print("  where you can actually see the pattern.")
    print("=" * 50)

    img = Image.new("1", (device.width, device.height), 0)
    draw = ImageDraw.Draw(img)
    _pattern_checkerboard(img, draw, size=4)
    device.display(img)

    for level in [0, 32, 64, 96, 128, 160, 192, 224, 255]:
        try:
            device.contrast(level)
        except Exception as e:
            print(f"  contrast({level}) raised {type(e).__name__}: {e} — driver may not support it.")
            return
        print(f"  contrast = {level:3d}")
        time.sleep(1.2)

    try:
        device.contrast(255)
    except Exception:
        pass
    print("\n  Left at max contrast (255). If the panel only became visible")
    print("  partway through the sweep, hardware_test.py should call")
    print("  device.contrast(...) after init to set it explicitly.")


# ─────────────────────────────────────────
# MENU
# ─────────────────────────────────────────

def main():
    print("=" * 50)
    print("  ProxiTalk V2 — Screen Diagnostic")
    print("=" * 50)
    print("  [0] Raw SDA/SCL pin check (start here if scan hangs)")
    print("  [1] I2C bus scan")
    print("  [2] Raw driver init test")
    print("  [3] Guided visual test")
    print("  [4] Contrast sweep")
    print("  [q] Quit")
    print("=" * 50)

    device = None
    while True:
        try:
            choice = input("Choice: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if choice == "0":
            raw_i2c_pin_check()
        elif choice == "1":
            i2c_bus_scan()
        elif choice == "2":
            device = raw_init_test() or device
        elif choice == "3":
            if device is None:
                print("  Run [2] first to initialize the display.")
            else:
                guided_visual_test(device)
        elif choice == "4":
            if device is None:
                print("  Run [2] first to initialize the display.")
            else:
                contrast_sweep(device)
        elif choice == "q":
            return
        else:
            print("Enter 0-4 or q.")


if __name__ == "__main__":
    main()
