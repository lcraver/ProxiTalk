#!/usr/bin/env python3
"""
ProxiTalk V2 — Combined Hardware Test
A menu-driven test for every piece of hardware. Pick a test to run, Ctrl+C
to return to the menu, 'q' to quit:
  [s] Screen — full flash on/off, alternating vertical lines, alternating
      horizontal lines, then off.
  [l] LEDs   — flash each of the 4 SK9822 RGB LEDs one after another.
  [k] Keyboard — live keypress tester.
  [t] Live transcription — continuous mic transcription, mirrored to the
      display, with each session's audio saved to a .wav.
  [r] Raw mic recording — unprocessed capture for comparison.

Run via SSH: python3 hardware_test.py
"""

import array
import audioop
import json
import math
import os
import re
import subprocess
import sys
import time
import wave

from PIL import Image, ImageDraw, ImageFont

import RPi.GPIO as GPIO
import spidev

from luma.core.interface.serial import i2c
from luma.oled.device import ssd1309

# ─────────────────────────────────────────
# SCREEN (SSD1309, 128x64, I2C)
# ─────────────────────────────────────────

DISPLAY_WIDTH = 128
DISPLAY_HEIGHT = 64
I2C_PORT = 1
I2C_ADDRESS = 0x3C


class ScreenHandle:
    """Wraps the OLED device so an unplugged/failed screen degrades to a
    no-op instead of crashing whichever test happens to touch the display."""

    def __init__(self, device):
        self.device = device

    @property
    def width(self):
        return self.device.width if self.device else DISPLAY_WIDTH

    @property
    def height(self):
        return self.device.height if self.device else DISPLAY_HEIGHT

    def show(self, img):
        if self.device is None:
            return
        try:
            self.device.display(img)
        except Exception as e:
            print(f"  Screen error ({e}); disabling display for the rest of this test.")
            self.device = None


def open_display():
    try:
        serial = i2c(port=I2C_PORT, address=I2C_ADDRESS)
        return ScreenHandle(ssd1309(serial))
    except Exception as e:
        print(f"Screen not detected ({e}); continuing without display.")
        return ScreenHandle(None)


def screen_test(handle, delay=0.5):
    if handle.device is None:
        print("Screen unavailable — skipping screen test.")
        return

    print("Running screen test...")
    w, h = handle.width, handle.height

    print("  Full flash on/off")
    for _ in range(3):
        handle.show(Image.new("1", (w, h), 255))
        time.sleep(delay)
        handle.show(Image.new("1", (w, h), 0))
        time.sleep(delay)

    print("  Alternating vertical lines")
    img = Image.new("1", (w, h), 0)
    draw = ImageDraw.Draw(img)
    for x in range(0, w, 2):
        draw.line([(x, 0), (x, h - 1)], fill=255)
    handle.show(img)
    time.sleep(delay * 2)

    print("  Alternating horizontal lines")
    img = Image.new("1", (w, h), 0)
    draw = ImageDraw.Draw(img)
    for y in range(0, h, 2):
        draw.line([(0, y), (w - 1, y)], fill=255)
    handle.show(img)
    time.sleep(delay * 2)

    print("  Off")
    handle.show(Image.new("1", (w, h), 0))


# ─────────────────────────────────────────
# LEDS (SK9822, 4x, SPI0)
# ─────────────────────────────────────────

NUM_LEDS = 4
BRIGHTNESS = 8  # 0-31, keep low for desk testing
SPI_BUS = 0
SPI_DEVICE = 0
SPI_SPEED_HZ = 1_000_000

LED_COLORS = [
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


def build_led_frame(pixels):
    frame = [0x00, 0x00, 0x00, 0x00]  # start frame
    for r, g, b in pixels:
        frame += [0xE0 | BRIGHTNESS, b, g, r]
    frame += [0xFF] * ((NUM_LEDS // 2) + 1)
    return frame


def led_show(spi, pixels):
    spi.xfer2(build_led_frame(pixels))


def led_all_off(spi):
    led_show(spi, [(0, 0, 0)] * NUM_LEDS)


def led_test(spi, delay=0.3):
    print("Flashing each RGB LED in order...")
    for i in range(NUM_LEDS):
        for name, color in LED_COLORS:
            pixels = [(0, 0, 0)] * NUM_LEDS
            pixels[i] = color
            led_show(spi, pixels)
            print(f"  LED {i} → {name}")
            time.sleep(delay)
        led_all_off(spi)
        time.sleep(delay / 2)


# ─────────────────────────────────────────
# MIC
# ─────────────────────────────────────────

RECORDINGS_DIR = "/tmp/hardware_test_recordings"

VOSK_RATE = 16000  # Vosk models expect 16kHz mono 16-bit PCM

# I2S mic (e.g. ICS-43434) native capture format — see mic_test.py. The mic
# shows up as one channel of a stereo S32_LE frame at 48kHz.
MIC_NATIVE_CHANNELS = 2
MIC_NATIVE_RATE = 48000
MIC_NATIVE_FORMAT = "S32_LE"

# The ICS-43434 being quiet at the ALSA level is a known, widely-reported
# characteristic (see Pi forum threads on "I2S microphone volume too low"),
# not something specific to this rig. The standard community fix is a fixed
# dB boost (e.g. via an ALSA softvol plugin) rather than an adaptive AGC —
# adaptive gain was overcomplicating this and causing pumping/ducking
# artifacts. A flat boost is simple and predictable: same gain every time.
MIC_GAIN_DB = 28.0
MIC_GAIN_LINEAR = 10 ** (MIC_GAIN_DB / 20)

# A persistent electrical tone shows up in recordings — present even during
# silence, picked up via the power supply/wiring rather than the room.
# Measured via FFT against an actual sample (not assumed): fundamental is
# ~53.2Hz, not the 50Hz mains grid — its 5th harmonic at ~266Hz dominates.
# Notch each harmonic out; narrow enough (high Q) to leave speech untouched.
MAINS_HUM_FREQS_HZ = [53.2, 106.4, 159.6, 212.8, 266.0]
NOTCH_Q = 12.0

# Noise gate, tuned to typical speech/podcast-gate recommendations rather
# than guessed: fast attack (1-3ms, so word onsets aren't clipped), a hold
# time so brief gaps between syllables/end of sentence don't trigger the
# release, and a release for a natural fade instead of an abrupt cutoff.
# Sentence-ends were still getting clipped at the lower end of the typical
# 100-300ms release range, so this sits at the slow/forgiving end of every
# range (longer hold, longer release, slower envelope decay, lower
# threshold) rather than the tight end. Runs on the raw, pre-gain signal
# (before _apply_fixed_gain) so the gate's threshold is independent of the
# boost.
NOISE_GATE_THRESHOLD = 40
NOISE_GATE_ENV_ATTACK = 1 - math.exp(-1 / (0.003 * VOSK_RATE))    # ~3ms envelope tracking
NOISE_GATE_ENV_RELEASE = 1 - math.exp(-1 / (0.1 * VOSK_RATE))     # ~100ms envelope tracking
NOISE_GATE_OPEN_ATTACK = 1 - math.exp(-1 / (0.002 * VOSK_RATE))   # ~2ms gate opening
NOISE_GATE_CLOSE_RELEASE = 1 - math.exp(-1 / (0.3 * VOSK_RATE))   # ~300ms gate closing
NOISE_GATE_HOLD_SAMPLES = int(0.06 * VOSK_RATE)                   # ~60ms hold before release


def _noise_gate(pcm16_bytes, state, threshold=NOISE_GATE_THRESHOLD):
    """Sample-level noise gate: envelope follower + hold + smoothed gate
    gain (fast attack, held open briefly, slow release). `state` is
    (envelope, gate_gain, hold_counter)."""
    envelope, gate_gain, hold_counter = state
    samples = array.array('h')
    samples.frombytes(pcm16_bytes)
    out = array.array('h', bytes(len(pcm16_bytes)))
    for i, x in enumerate(samples):
        level = abs(x)
        env_alpha = NOISE_GATE_ENV_ATTACK if level > envelope else NOISE_GATE_ENV_RELEASE
        envelope += (level - envelope) * env_alpha

        if envelope > threshold:
            hold_counter = NOISE_GATE_HOLD_SAMPLES
            desired_gain = 1.0
        elif hold_counter > 0:
            hold_counter -= 1
            desired_gain = 1.0
        else:
            desired_gain = 0.0

        gain_alpha = NOISE_GATE_OPEN_ATTACK if desired_gain > gate_gain else NOISE_GATE_CLOSE_RELEASE
        gate_gain += (desired_gain - gate_gain) * gain_alpha

        out[i] = max(-32768, min(32767, int(x * gate_gain)))
    return out.tobytes(), (envelope, gate_gain, hold_counter)


def _notch_coeffs(freq, fs, q):
    """RBJ audio-EQ-cookbook biquad notch coefficients, normalized by a0."""
    w0 = 2 * math.pi * freq / fs
    alpha = math.sin(w0) / (2 * q)
    cos_w0 = math.cos(w0)
    a0 = 1 + alpha
    return (1 / a0, -2 * cos_w0 / a0, 1 / a0, -2 * cos_w0 / a0, (1 - alpha) / a0)


_NOTCH_FILTER_COEFFS = [_notch_coeffs(f, VOSK_RATE, NOTCH_Q) for f in MAINS_HUM_FREQS_HZ]


def _apply_notch(pcm16_bytes, coeffs, state):
    """Apply one biquad notch. `state` is (x1, x2, y1, y2)."""
    b0, b1, b2, a1, a2 = coeffs
    x1, x2, y1, y2 = state
    samples = array.array('h')
    samples.frombytes(pcm16_bytes)
    out = array.array('h', bytes(len(pcm16_bytes)))
    for i, x0 in enumerate(samples):
        y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1 = x1, x0
        y2, y1 = y1, y0
        out[i] = max(-32768, min(32767, int(y0)))
    return out.tobytes(), (x1, x2, y1, y2)


def _remove_mains_hum(pcm16_bytes, notch_states):
    """Cascade a notch filter per hum harmonic. Mutates `notch_states` in place."""
    for i, coeffs in enumerate(_NOTCH_FILTER_COEFFS):
        pcm16_bytes, notch_states[i] = _apply_notch(pcm16_bytes, coeffs, notch_states[i])
    return pcm16_bytes


RAW_RECORD_DURATION_SEC = 5


def record_raw_test(alsa_device="default"):
    """Record straight from the mic to a .wav with zero processing — native
    format/rate, no channel selection, no gain, no filtering. Useful as a
    ground-truth comparison against the processed transcription recordings."""
    if alsa_device == "default":
        detected = find_capture_device()
        if detected:
            print(f"Resolved 'default' capture device to '{detected}'.")
            alsa_device = detected

    os.makedirs(RECORDINGS_DIR, exist_ok=True)
    recording_path = os.path.join(
        RECORDINGS_DIR, f"raw_{time.strftime('%Y%m%d_%H%M%S')}.wav"
    )

    print("=" * 40)
    print("  Raw Mic Recording (unprocessed)")
    print(f"  Device: '{alsa_device}'")
    print(f"  Recording {RAW_RECORD_DURATION_SEC}s — speak now...")
    print("=" * 40)

    cmd = [
        "arecord",
        "-D", alsa_device,
        "-c", str(MIC_NATIVE_CHANNELS),
        "-r", str(MIC_NATIVE_RATE),
        "-f", MIC_NATIVE_FORMAT,
        "-d", str(RAW_RECORD_DURATION_SEC),
        recording_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("arecord failed:")
        print(result.stderr)
        return

    print(f"Saved raw recording to {recording_path}")


def _apply_fixed_gain(pcm16_bytes, linear_gain=MIC_GAIN_LINEAR):
    """Flat dB boost — audioop.mul clips automatically, so this is safe
    against overflow, just not adaptive (a loud sound stays loud relative
    to a quiet one, like a real preamp gain knob rather than a compressor)."""
    if linear_gain <= 1.01:
        return pcm16_bytes
    return audioop.mul(pcm16_bytes, 2, linear_gain)


def find_capture_device():
    """Resolve the first real capture-capable ALSA device (card/device) via `arecord -l`.

    `default` is usually routed through dmix, which is playback-only, so it
    can't be used to record — this finds an actual hw card to use instead.
    """
    result = subprocess.run(["arecord", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    match = re.search(r"card (\d+):.*device (\d+):", result.stdout)
    if not match:
        return None
    card, device = match.group(1), match.group(2)
    return f"plughw:{card},{device}"


VOSK_MODEL_PATH = os.path.expanduser("~/vosk-model")
_vosk_model = None  # cached across calls so re-entering the test doesn't reload from disk


def live_transcribe_test(alsa_device="default", model_path=VOSK_MODEL_PATH, device=None):
    """Continuously listen on the mic and print transcribed words as they're heard."""
    try:
        from vosk import Model, KaldiRecognizer
    except ImportError:
        print("Live transcription unavailable: vosk isn't installed.")
        print("  pip3 install vosk")
        return

    if not os.path.isdir(model_path):
        print(f"Live transcription unavailable: no Vosk model found at '{model_path}'.")
        print("  Download a small model (e.g. vosk-model-small-en-us-0.15) from")
        print("  https://alphacephei.com/vosk/models and unzip it to that path.")
        return

    if alsa_device == "default":
        detected = find_capture_device()
        if detected:
            alsa_device = detected

    print("=" * 40)
    print("  Live Transcription Tester")
    print(f"  Device: '{alsa_device}'")
    print("=" * 40)

    global _vosk_model
    if _vosk_model is None:
        print("Loading Vosk model...")
        _vosk_model = Model(model_path)
    rec = KaldiRecognizer(_vosk_model, VOSK_RATE)
    rec.SetWords(True)

    if device is not None:
        show_status(device, "LOADING...")

    # Capture at the mic's native format/rate (32-bit, 48kHz, I2S mic appears
    # as one channel of a stereo frame — see mic_test.py) instead of asking
    # ALSA to convert straight to 16-bit/16kHz: that conversion is naive and
    # loses most of the effective signal level, making the mic sound far
    # quieter than it actually is.
    cmd = [
        "arecord",
        "-D", alsa_device,
        "-c", str(MIC_NATIVE_CHANNELS),
        "-r", str(MIC_NATIVE_RATE),
        "-f", MIC_NATIVE_FORMAT,
        "-t", "raw",
        "--buffer-size=24000",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # arecord takes a moment to actually open the device — wait for it before
    # telling the user it's safe to speak, otherwise the first words get missed.
    time.sleep(0.5)

    print()
    print("*" * 40)
    print("  >>> READY — start speaking now <<<")
    print("*" * 40)

    if device is not None:
        show_status(device, "LISTENING...")
        time.sleep(0.4)
        device.show(Image.new("1", (device.width, device.height), 0))

    recording_path = os.path.join(
        RECORDINGS_DIR, f"transcription_{time.strftime('%Y%m%d_%H%M%S')}.wav"
    )
    os.makedirs(RECORDINGS_DIR, exist_ok=True)
    wav_out = wave.open(recording_path, "wb")
    wav_out.setnchannels(1)
    wav_out.setsampwidth(2)  # S16_LE
    wav_out.setframerate(VOSK_RATE)

    frame_bytes = MIC_NATIVE_CHANNELS * 4  # 4 bytes/sample at S32_LE
    read_size = frame_bytes * (MIC_NATIVE_RATE // 4)  # ~0.25s of audio at a time
    louder_channel = None  # determined from the first chunk, then locked in
    ratecv_state = None
    notch_states = [(0.0, 0.0, 0.0, 0.0) for _ in MAINS_HUM_FREQS_HZ]
    gate_state = (0.0, 0.0, 0)

    spoken_words = []   # words already printed for the utterance in progress
    display_words = []  # rolling history of words shown on screen
    try:
        while True:
            raw = proc.stdout.read(read_size)
            if not raw:
                break
            # Truncate to a whole number of frames in case of a short read.
            raw = raw[: len(raw) - (len(raw) % frame_bytes)]
            if not raw:
                continue

            channels = [
                audioop.tomono(raw, 4, 1 if ch == 0 else 0, 1 if ch == 1 else 0)
                for ch in range(MIC_NATIVE_CHANNELS)
            ]

            if louder_channel is None:
                rms_per_channel = [audioop.rms(ch, 4) for ch in channels]
                louder_channel = rms_per_channel.index(max(rms_per_channel))

            mono_32 = channels[louder_channel]
            mono_16 = audioop.lin2lin(mono_32, 4, 2)
            mono_16, ratecv_state = audioop.ratecv(
                mono_16, 2, 1, MIC_NATIVE_RATE, VOSK_RATE, ratecv_state
            )
            # Gate runs before the hum notches: two of the notch frequencies
            # (106.4/159.6Hz) sit inside typical voice fundamental range, so
            # gating after notching could read a voiced word as quiet enough
            # to close, clipping whole words.
            mono_16, gate_state = _noise_gate(mono_16, gate_state)
            mono_16 = _remove_mains_hum(mono_16, notch_states)
            mono_16 = _apply_fixed_gain(mono_16)

            wav_out.writeframes(mono_16)
            if rec.AcceptWaveform(mono_16):
                result = json.loads(rec.Result())
                words = result.get("text", "").strip().split()
                _print_new_words(words, spoken_words, display_words, device)
                if spoken_words:
                    print()  # end the utterance's line
                spoken_words = []
            else:
                partial = json.loads(rec.PartialResult()).get("partial", "").strip()
                _print_new_words(partial.split(), spoken_words, display_words, device)
    except KeyboardInterrupt:
        if spoken_words:
            print()
        print("\nExiting live transcription test.")
    finally:
        proc.terminate()
        proc.wait()
        wav_out.close()
        print(f"Saved recording to {recording_path}")


def _print_new_words(words, spoken_words, display_words, device):
    """Print only the words in `words` beyond what's already in `spoken_words`,
    streaming new words one at a time, and mirror them to the display.
    Mutates `spoken_words`/`display_words` in place."""
    if not words[:len(spoken_words)] == spoken_words:
        # Vosk revised earlier words — not worth reconciling, just resync silently.
        spoken_words[:] = words
        return
    new_words = words[len(spoken_words):]
    if not new_words:
        return
    if not spoken_words:
        print("  Heard: ", end="", flush=True)
    print(" ".join(new_words) + " ", end="", flush=True)
    spoken_words.extend(new_words)

    if device is not None:
        display_words.extend(new_words)
        render_transcript(device, display_words)


_transcript_font = None


def show_status(device, text):
    """Render a single centered status line, e.g. 'LISTENING...'."""
    global _transcript_font
    if _transcript_font is None:
        _transcript_font = ImageFont.load_default()

    img = Image.new("1", (device.width, device.height), 0)
    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0, 0), text, font=_transcript_font)
    x = max(0, (device.width - (bbox[2] - bbox[0])) // 2)
    y = max(0, (device.height - (bbox[3] - bbox[1])) // 2)
    draw.text((x, y), text, fill=255, font=_transcript_font)
    device.show(img)


def render_transcript(device, words, line_height=10, max_words_kept=60):
    """Render a word-wrapped, scrolling transcript to the display."""
    global _transcript_font
    if _transcript_font is None:
        _transcript_font = ImageFont.load_default()

    # Keep the word list from growing forever during a long session.
    del words[:-max_words_kept]

    img = Image.new("1", (device.width, device.height), 0)
    draw = ImageDraw.Draw(img)

    lines = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textbbox((0, 0), trial, font=_transcript_font)[2] > device.width and current:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)

    max_lines = max(1, device.height // line_height)
    for i, line in enumerate(lines[-max_lines:]):
        draw.text((0, i * line_height), line, fill=255, font=_transcript_font)

    device.show(img)


# ─────────────────────────────────────────
# KEYBOARD MATRIX (5x10)
# ─────────────────────────────────────────

# Matched to Netlist_Schematic1_2026-06-30.tel (PI1 header, BCM numbering)
COLS = [4, 17, 27, 22, 23, 24, 25, 8, 7, 16]   # COL0 → COL9
ROWS = [5, 6, 13, 26, 12]                       # ROW0 → ROW4

KEYMAP = [
    # COL0    COL1     COL2    COL3    COL4      COL5      COL6    COL7     COL8    COL9
    [ 'FN1',  'SHIFT', 'ALT',  '<',    'SPACE1', 'SPACE2', '>',    'CMD',   'CTRL', 'FN2'   ],  # ROW0
    [ 'Z',    'X',     'C',    'V',    'B',      'N',      'M',    'COLON', 'COMMA','ENTER' ],  # ROW1
    [ 'A',    'S',     'D',    'F',    'G',      'H',      'J',    'K',     'L',    'DEL'   ],  # ROW2
    [ 'Q',    'W',     'E',    'R',    'T',      'Y',      'U',    'I',     'O',    'P'     ],  # ROW3
    [ '1',    '2',     '3',    '4',    '5',      '6',      '7',    '8',     '9',    '0'     ],  # ROW4
]


def matrix_setup():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    for row in ROWS:
        GPIO.setup(row, GPIO.OUT)
        GPIO.output(row, GPIO.HIGH)

    for col in COLS:
        GPIO.setup(col, GPIO.IN, pull_up_down=GPIO.PUD_UP)


def matrix_scan():
    pressed = []
    for row_idx, row_pin in enumerate(ROWS):
        GPIO.output(row_pin, GPIO.LOW)
        time.sleep(0.001)
        for col_idx, col_pin in enumerate(COLS):
            if GPIO.input(col_pin) == GPIO.LOW:
                pressed.append((row_idx, col_idx))
        GPIO.output(row_pin, GPIO.HIGH)
    return pressed


def keyboard_test():
    print("=" * 40)
    print("  Keyboard Tester")
    print("  Press any key to test, Ctrl+C to exit")
    print("=" * 40)

    matrix_setup()
    last_pressed = set()

    try:
        while True:
            pressed_set = set(matrix_scan())
            new_keys = pressed_set - last_pressed
            for (row, col) in new_keys:
                key = KEYMAP[row][col]
                print(f"KEY PRESSED → {key:10s}  (row={row}, col={col})")
            last_pressed = pressed_set
            time.sleep(0.02)
    except KeyboardInterrupt:
        print("\nExiting keyboard test.")
    finally:
        GPIO.cleanup()


def final_test_menu(alsa_device, device):
    """Let the user pick freely between the available hardware tests."""
    print("=" * 40)
    print("  Hardware Tests")
    print("  [s] Screen test")
    print("  [l] LED test")
    print("  [k] Keyboard tester")
    print("  [t] Live transcription")
    print("  [r] Raw mic recording (unprocessed)")
    print("  [q] Quit")
    print("  (Ctrl+C inside a test returns you here)")
    print("=" * 40)

    while True:
        try:
            choice = input("Choice: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if choice == "s":
            screen_test(device)
        elif choice == "l":
            spi = open_spi()
            try:
                led_test(spi)
            finally:
                led_all_off(spi)
                spi.close()
        elif choice == "k":
            keyboard_test()
        elif choice == "t":
            live_transcribe_test(alsa_device, device=device)
        elif choice == "r":
            record_raw_test(alsa_device)
        elif choice == "q":
            return
        else:
            print("Enter 's', 'l', 'k', 't', 'r', or 'q'.")


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

def main():
    alsa_device = sys.argv[1] if len(sys.argv) > 1 else "default"

    print("=" * 40)
    print("  ProxiTalk V2 — Hardware Test")
    print("=" * 40)

    display = open_display()
    final_test_menu(alsa_device, display)


if __name__ == "__main__":
    main()
