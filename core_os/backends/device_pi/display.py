"""Real hardware display driver — ssd1309 OLED over I2C via luma.oled.
Ports emulator_display.LumaDisplayWrapper behind the DisplayDriver contract."""

from __future__ import annotations

import time

from core_os.core.drivers.base import DisplayDriver

I2C_PORT = 1
I2C_ADDRESS = 0x3C


class LumaDisplayDriver(DisplayDriver):
    def __init__(self, i2c_port: int = I2C_PORT, i2c_address: int = I2C_ADDRESS) -> None:
        from luma.core.interface.serial import i2c
        from luma.oled.device import ssd1309

        serial = i2c(port=i2c_port, address=i2c_address)
        self._device = ssd1309(serial)
        self.width = self._device.width
        self.height = self._device.height

    def fill(self, color: int) -> None:
        from PIL import Image

        self._device.display(Image.new("1", (self.width, self.height), color))

    def image(self, img) -> None:
        self._device.display(img)

    def show(self) -> None:
        pass  # device.display() already flushes

    def contrast(self, level: int) -> None:
        self._device.contrast(level)

    def stop(self) -> None:
        self._device.cleanup()


# 2.13" reflective LCD, 250x122 physical / 250x120 addressable (bottom 2 rows
# are hardware-dead on this controller — see vendor's own MicroPython driver
# comment). Protocol ported from elulis/micropython_ST7302 (st7302.py, MIT),
# swapping machine.Pin/machine.SPI for RPi.GPIO/spidev. Init sequence, panel
# register values, and the _convert() bit layout are the vendor's — do not
# "clean up" the magic numbers, they're what the controller expects.
SPI_BUS = 0
SPI_DEVICE = 0
SPI_HZ = 40_000_000
CS_PIN = 8  # BCM — TODO: confirm against actual wiring
DC_PIN = 25  # BCM — TODO: confirm against actual wiring
RST_PIN = 24  # BCM — TODO: confirm against actual wiring

_PANEL_WIDTH = 250
_PANEL_HEIGHT = 122
_ROWS_ADDRESSABLE = 120  # 15 bytes/column * 8; rows 120-121 are hardware-dead (controller has no
# page RAM for them at all — fixed at the bottom, not something a column-style offset can move)
_ROW_TOP_BLANK = 1  # row 0 of the addressable window is sacrificed on purpose (never written) so
# there's a top border too, not just the forced 2-row dead zone at the bottom. Can't go to 0/2 —
# the 2 bottom rows are a hard controller limit (buffer/protocol only ever cover 120 of 122 rows),
# so top+bottom end up 1px/2px, not perfectly symmetric.
_ROWS_CONTENT = _ROWS_ADDRESSABLE - _ROW_TOP_BLANK  # 119 — what apps actually get to draw into
_TOP_BLANK_MASK = (1 << _ROW_TOP_BLANK) - 1  # bit 0 of band 0 — must always read 0
_COLS_ADDRESSABLE = 248  # 2 columns kept as a permanently-blank border, split evenly since column
# addressing is plain buffer indexing (no protocol constant tied to it, unlike the dead rows)
_COL_OFFSET = (_PANEL_WIDTH - _COLS_ADDRESSABLE) // 2
_BANDS = _ROWS_ADDRESSABLE // 8


class ST7302DisplayDriver(DisplayDriver):
    def __init__(
        self,
        spi_bus: int = SPI_BUS,
        spi_device: int = SPI_DEVICE,
        cs_pin: int = CS_PIN,
        dc_pin: int = DC_PIN,
        rst_pin: int = RST_PIN,
    ) -> None:
        import spidev
        import RPi.GPIO as GPIO

        self.width = _COLS_ADDRESSABLE
        self.height = _ROWS_CONTENT
        self._gpio = GPIO
        self._cs = cs_pin
        self._dc = dc_pin
        self._rst = rst_pin

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(cs_pin, GPIO.OUT, initial=GPIO.HIGH)
        GPIO.setup(dc_pin, GPIO.OUT, initial=GPIO.HIGH)
        GPIO.setup(rst_pin, GPIO.OUT, initial=GPIO.HIGH)

        self._spi = spidev.SpiDev()
        self._spi.open(spi_bus, spi_device)
        self._spi.max_speed_hz = SPI_HZ
        self._spi.mode = 0

        # bs: MONO_VLSB framebuffer, band-major (15 bands * 8 rows = 120 rows)
        self._bs = bytearray(_PANEL_WIDTH * _BANDS)
        # bt: packed transfer buffer in the layout the controller expects
        self._bt = bytearray(125 * 10 * 3)
        self._inverted = False

        self._init_panel()

    def _cmd(self, command: int, data=None) -> None:
        self._gpio.output(self._dc, 0)
        self._gpio.output(self._cs, 0)
        self._spi.writebytes([command])
        self._gpio.output(self._cs, 1)
        self._gpio.output(self._dc, 1)
        if data:
            self._gpio.output(self._cs, 0)
            self._spi.writebytes(list(data))
            self._gpio.output(self._cs, 1)

    def _init_panel(self) -> None:
        time.sleep(0.05)
        self._gpio.output(self._rst, 0)
        time.sleep(0.1)
        self._gpio.output(self._rst, 1)

        commands = [
            (0xEB, [0x02]),  # Enable OTP
            (0xD7, [0x68]),  # OTP Load Control
            (0xC0, [0x80]),  # Gate Voltage Setting VGH=12V ; VGL=-5V
            (0xC1, [0x28, 0x28, 0x28, 0x28, 0x14, 0x00]),  # VSH Setting
            (0xC2, [0x00, 0x00, 0x00, 0x00]),  # VSL Setting VSL=0
            (0xCB, [0x14]),  # VCOMH Setting
            (0xB4, [0xA5, 0x66, 0x01, 0x00, 0x00, 0x40, 0x01, 0x00, 0x00, 0x40]),  # Gate EQ Setting
            (0x11, []),  # Sleep out
            100,
            (0x36, [0x00]),  # Memory Data Access Control
            (0x3A, [0x11]),  # Data Format Select
            (0xB0, [0x64]),  # Duty Setting
            (0xB8, [0x09]),  # Panel Setting: frame inversion
            (0xB2, [0x01, 0x05]),  # Frame Rate Control
            (0x39, []),  # LPM
            (0x29, []),  # Display on
            100,
        ]
        for entry in commands:
            if isinstance(entry, tuple):
                self._cmd(entry[0], entry[1])
            else:
                time.sleep(entry / 1000)

        self.fill(0)
        self._cmd(0x2A, [0x19 + 10, 0x19 + 10])
        self._cmd(0x2B, [0x00, 0x00 + 125 - 1])
        self._cmd(0x2C, self._bs[0 : 125 * 3])

    def fill(self, color: int) -> None:
        # Only the addressable columns are touched, offset to center them —
        # the 1px left/right border must never take a fill. Band 0 additionally
        # keeps its top-blank bits (rows 0-1) forced to 0 regardless of color.
        fill_byte = 0xFF if color else 0x00
        for band in range(_BANDS):
            base = band * _PANEL_WIDTH
            band_byte = fill_byte & ~_TOP_BLANK_MASK if band == 0 else fill_byte
            for x in range(_COLS_ADDRESSABLE):
                self._bs[base + x + _COL_OFFSET] = band_byte

    def image(self, img) -> None:
        px = img.load()
        w, h = img.size
        rows = min(h, _ROWS_CONTENT)
        for band in range(_BANDS):
            base = band * _PANEL_WIDTH
            for x in range(min(w, _COLS_ADDRESSABLE)):
                byte = 0
                for bit in range(8):
                    # physical row within the addressable window, shifted back
                    # to a content row by the sacrificed top rows
                    content_y = band * 8 + bit - _ROW_TOP_BLANK
                    if 0 <= content_y < rows and px[x, content_y]:
                        byte |= 1 << bit
                self._bs[base + x + _COL_OFFSET] = byte

    def _convert(self) -> None:
        s = self._bs
        t = self._bt
        k = 0
        for i in range(0, _PANEL_WIDTH, 2):
            for j in range(0, _BANDS, 3):
                for y in range(0, 3):
                    b1 = s[(j + y) * _PANEL_WIDTH + i + 0]
                    b2 = s[(j + y) * _PANEL_WIDTH + i + 1]
                    mix = (
                        ((b1 & 0x01) << 7)
                        | ((b2 & 0x01) << 6)
                        | ((b1 & 0x02) << 4)
                        | ((b2 & 0x02) << 3)
                        | ((b1 & 0x04) << 1)
                        | ((b2 & 0x04) << 0)
                        | ((b1 & 0x08) >> 2)
                        | ((b2 & 0x08) >> 3)
                    )
                    t[k] = mix
                    k += 1

                    b1 >>= 4
                    b2 >>= 4
                    mix = (
                        ((b1 & 0x01) << 7)
                        | ((b2 & 0x01) << 6)
                        | ((b1 & 0x02) << 4)
                        | ((b2 & 0x02) << 3)
                        | ((b1 & 0x04) << 1)
                        | ((b2 & 0x04) << 0)
                        | ((b1 & 0x08) >> 2)
                        | ((b2 & 0x08) >> 3)
                    )
                    t[k] = mix
                    k += 1

    def show(self) -> None:
        self._convert()
        self._cmd(0x2A, [0x19, 0x19 + 10 - 1])
        self._cmd(0x2B, [0x00, 0x00 + 125 - 1])
        self._cmd(0x2C, self._bt)

    def contrast(self, level: int) -> None:
        pass  # no runtime contrast register wired up — VCOMH is set once at init

    def invert(self, flag: bool) -> None:
        if flag == self._inverted:
            return
        self._inverted = flag
        # Border columns are excluded from the flip for the same reason
        # they're excluded from fill() — they must stay blank, always. Band 0
        # only flips its non-blank bits so rows 0-1 never come back to life.
        flip_mask = 0xFF & ~_TOP_BLANK_MASK
        for band in range(_BANDS):
            base = band * _PANEL_WIDTH
            band_flip = flip_mask if band == 0 else 0xFF
            for x in range(_COLS_ADDRESSABLE):
                self._bs[base + x + _COL_OFFSET] ^= band_flip

    def stop(self) -> None:
        self._spi.close()
        self._gpio.cleanup((self._cs, self._dc, self._rst))
