#!/usr/bin/env python3
"""
ProxiTalk V2 — SK9822 LED Test
Cycles 4 SK9822 (APA102-compatible) LEDs on/off in order, then runs
each LED through an RGB test pattern.
Data = GPIO10 (SDI/MOSI), Clock = GPIO11 (CKI/SCLK) — hardware SPI0.
Run via SSH: python3 led_test.py
Press Ctrl+C to exit.
"""

import spidev
import time

NUM_LEDS = 4
BRIGHTNESS = 8  # 0-31, keep low for desk testing

SPI_BUS = 0
SPI_DEVICE = 0
SPI_SPEED_HZ = 1_000_000

COLORS = [
    ('RED',   (255, 0,   0)),
    ('GREEN', (0,   255, 0)),
    ('BLUE',  (0,   0,   255)),
    ('WHITE', (255, 255, 255)),
]


def open_spi():
    spi = spidev.SpiDev()
    spi.open(SPI_BUS, SPI_DEVICE)
    spi.max_speed_hz = SPI_SPEED_HZ
    spi.mode = 0b00
    return spi


def build_frame(pixels):
    """pixels: list of (r, g, b) tuples, length NUM_LEDS."""
    frame = [0x00, 0x00, 0x00, 0x00]  # start frame
    for r, g, b in pixels:
        frame += [0xE0 | BRIGHTNESS, b, g, r]  # SK9822 frame: brightness, B, G, R
    # end frame — at least (NUM_LEDS / 2) bits of 1, rounded up to bytes
    frame += [0xFF] * ((NUM_LEDS // 2) + 1)
    return frame


def show(spi, pixels):
    spi.xfer2(build_frame(pixels))


def all_off(spi):
    show(spi, [(0, 0, 0)] * NUM_LEDS)


def cycle_on_off(spi, delay=0.3):
    """Light each LED white, one at a time, in order."""
    print("Cycling LEDs on/off in order...")
    for i in range(NUM_LEDS):
        pixels = [(0, 0, 0)] * NUM_LEDS
        pixels[i] = (255, 255, 255)
        show(spi, pixels)
        print(f"  LED {i} ON")
        time.sleep(delay)
        all_off(spi)
        time.sleep(delay / 2)


def rgb_test(spi, delay=0.4):
    """Step each LED through red, green, blue, white."""
    print("Running RGB test on each LED...")
    for i in range(NUM_LEDS):
        for name, color in COLORS:
            pixels = [(0, 0, 0)] * NUM_LEDS
            pixels[i] = color
            show(spi, pixels)
            print(f"  LED {i} → {name}")
            time.sleep(delay)
        all_off(spi)


def main():
    spi = open_spi()
    print("=" * 40)
    print("  ProxiTalk V2 — SK9822 LED Test")
    print("  Ctrl+C to exit")
    print("=" * 40)

    try:
        while True:
            cycle_on_off(spi)
            rgb_test(spi)
    except KeyboardInterrupt:
        print("\nExiting LED test.")
    finally:
        all_off(spi)
        spi.close()


if __name__ == "__main__":
    main()
