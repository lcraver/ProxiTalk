#!/usr/bin/env python3
"""
ProxiTalk V2 — I2S Mic Test
Records a few seconds of audio from the I2S mic (MIC1) via arecord,
reports signal level, then attempts an offline transcription with Vosk
so you can confirm the mic is actually capturing intelligible speech.

Requires the I2S overlay to be enabled first (see setup steps) and
ALSA to list a capture device — check with `arecord -l`.

Transcription requires:
  pip3 install vosk
  a small Vosk model, e.g. vosk-model-small-en-us-0.15, unzipped to
  ~/vosk-model (or pass a path with --model)

Run via SSH: python3 mic_test.py [alsa_device] [--model PATH]
Default device is "default" — pass the exact ALSA device name
(e.g. plughw:1,0) if arecord -l shows something else.
"""

import subprocess
import sys
import wave
import audioop
import os
import json

DURATION_SEC = 5
SAMPLE_RATE = 48000
CHANNELS = 2          # I2S mics often appear as one channel of a stereo frame
SAMPLE_FORMAT = "S32_LE"
OUT_FILE = "/tmp/mic_test.wav"

SILENCE_THRESHOLD = 50  # RMS below this = likely no signal

VOSK_RATE = 16000  # Vosk models expect 16kHz mono 16-bit PCM
DEFAULT_MODEL_PATH = os.path.expanduser("~/vosk-model")


def record(device):
    print(f"Recording {DURATION_SEC}s from '{device}'... make some noise / tap the mic now.")
    cmd = [
        "arecord",
        "-D", device,
        "-c", str(CHANNELS),
        "-r", str(SAMPLE_RATE),
        "-f", SAMPLE_FORMAT,
        "-d", str(DURATION_SEC),
        OUT_FILE,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("arecord failed:")
        print(result.stderr)
        print("\nRun `arecord -l` to confirm the device name/index, then pass it as an argument:")
        print("  python3 mic_test.py plughw:1,0")
        sys.exit(1)


def analyze():
    with wave.open(OUT_FILE, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    mono_channels = []
    rms_per_channel = []
    for ch in range(n_channels):
        mono = audioop.tomono(frames, sampwidth, 1, 0) if ch == 0 else audioop.tomono(frames, sampwidth, 0, 1)
        mono_channels.append(mono)
        rms_per_channel.append(audioop.rms(mono, sampwidth))

    print("\nResults:")
    for i, rms in enumerate(rms_per_channel):
        status = "OK — signal detected" if rms > SILENCE_THRESHOLD else "silent / no signal"
        print(f"  Channel {i}: RMS={rms:6d}  ({status})")

    if max(rms_per_channel) <= SILENCE_THRESHOLD:
        print("\nNo signal on any channel. Check: overlay enabled + rebooted, "
              "correct ALSA device name, mic wiring (GPIO18/19/20), and that "
              "you made noise during the recording window.")
        return None

    loudest = rms_per_channel.index(max(rms_per_channel))
    print(f"\nMic is alive on channel {loudest}.")
    return mono_channels[loudest], sampwidth, framerate


def transcribe(mono_pcm, sampwidth, framerate, model_path):
    try:
        from vosk import Model, KaldiRecognizer
    except ImportError:
        print("\nSkipping transcription: vosk isn't installed.")
        print("  pip3 install vosk")
        return

    if not os.path.isdir(model_path):
        print(f"\nSkipping transcription: no Vosk model found at '{model_path}'.")
        print("  Download a small model (e.g. vosk-model-small-en-us-0.15) from")
        print("  https://alphacephei.com/vosk/models and unzip it to that path,")
        print("  or pass --model /path/to/model")
        return

    # Convert to 16-bit (if needed) then resample to the rate Vosk expects
    pcm = mono_pcm if sampwidth == 2 else audioop.lin2lin(mono_pcm, sampwidth, 2)
    pcm16, _ = audioop.ratecv(pcm, 2, 1, framerate, VOSK_RATE, None)

    print("\nTranscribing...")
    model = Model(model_path)
    rec = KaldiRecognizer(model, VOSK_RATE)
    rec.SetWords(True)

    chunk_size = 4000
    for i in range(0, len(pcm16), chunk_size):
        rec.AcceptWaveform(pcm16[i:i + chunk_size])

    result = json.loads(rec.FinalResult())
    text = result.get("text", "").strip()

    print("=" * 40)
    if text:
        print(f"  Heard: \"{text}\"")
    else:
        print("  (no speech recognized)")
    print("=" * 40)


def main():
    args = sys.argv[1:]
    model_path = DEFAULT_MODEL_PATH
    if "--model" in args:
        idx = args.index("--model")
        model_path = args[idx + 1]
        del args[idx:idx + 2]

    device = args[0] if args else "default"

    record(device)
    result = analyze()
    if result:
        mono_pcm, sampwidth, framerate = result
        transcribe(mono_pcm, sampwidth, framerate, model_path)
    os.remove(OUT_FILE)


if __name__ == "__main__":
    main()
