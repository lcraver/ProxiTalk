"""Audio playback helpers shared across ProxiTalk apps."""

from __future__ import annotations

import io
import os
import platform
import subprocess
import threading
import time
import wave

import pygame

IS_WINDOWS = platform.system() == "Windows"
MIXER_SETTINGS = {"frequency": 22050, "size": -16, "channels": 1}


def _ensure_mixer_initialized() -> None:
    """Make sure pygame's mixer is ready before playing audio."""
    try:
        if pygame.mixer.get_init():
            return
    except pygame.error as exc:
        print(f"[Audio] Mixer state check failed: {exc}")
    try:
        pygame.mixer.init(**MIXER_SETTINGS)
        print(
            f"[Audio] Pygame mixer initialized: {MIXER_SETTINGS['frequency']}Hz, 16-bit mono",
            flush=True,
        )
    except pygame.error as exc:
        print(f"[Audio] Failed to initialize pygame mixer: {exc}", flush=True)


def initialize_audio_system() -> None:
    """Public hook to initialize pygame mixer with consistent settings."""
    _ensure_mixer_initialized()


def play_sfx_internal(path: str) -> None:
    if not os.path.isfile(path):
        print(f"[Audio] File not found: {path}", flush=True)
        return

    try:
        if IS_WINDOWS:
            _ensure_mixer_initialized()
            sound = pygame.mixer.Sound(path)
            channel = sound.play()
            while channel.get_busy():
                pygame.time.wait(10)
        else:
            proc = subprocess.Popen(
                ["timeout", "10", "aplay", path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            _, stderr = proc.communicate()
            if proc.returncode not in (0, 124):
                print(
                    f"[Audio] aplay failed for SFX '{path}' with return code {proc.returncode}: {stderr.decode()}",
                    flush=True,
                )
    except Exception as exc:
        print(f"[Audio] Error playing wav file '{path}': {exc}", flush=True)


def play_sfx(path: str) -> None:
    threading.Thread(target=play_sfx_internal, args=(path,), daemon=True).start()


class AudioStreamer:
    def __init__(self) -> None:
        self.is_streaming = False
        self.stream_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.current_audio_file: str | None = None
        self.start_time = 0.0
        self.pause_time = 0.0
        self.is_paused = False
        self.volume = 0.7

    def start_stream(self, audio_file_path: str, start_offset: float = 0.0) -> bool:
        if not os.path.isfile(audio_file_path):
            print(f"[AudioStream] File not found: {audio_file_path}", flush=True)
            return False

        try:
            _ensure_mixer_initialized()
            mixer_info = pygame.mixer.get_init()
            print(f"[AudioStream] Pygame mixer settings: {mixer_info}", flush=True)
        except Exception as exc:
            print(f"[AudioStream] Error checking pygame mixer: {exc}", flush=True)
            return False

        print(f"[AudioStream] Starting stream for: {audio_file_path}", flush=True)

        self.stop_stream()
        self._stop_event.clear()
        self.current_audio_file = audio_file_path
        self.is_streaming = True
        self.is_paused = False
        self.start_time = time.time() - start_offset
        self.pause_time = 0.0

        try:
            self.stream_thread = threading.Thread(
                target=self._stream_audio_loop,
                args=(audio_file_path, start_offset),
                daemon=True,
            )
            self.stream_thread.start()
            print("[AudioStream] Stream thread started", flush=True)
            return True
        except Exception as exc:
            print(f"[AudioStream] Error starting stream thread: {exc}", flush=True)
            self.is_streaming = False
            return False

    def _stream_audio_loop(self, audio_file_path: str, start_offset: float) -> None:
        try:
            print(f"[AudioStream] Loading audio file: {audio_file_path}", flush=True)
            sound = pygame.mixer.Sound(audio_file_path)
            sound.set_volume(self.volume)

            print(f"[AudioStream] Starting playback (offset: {start_offset}s)", flush=True)
            channel = sound.play()
            if not channel:
                print("[AudioStream] Failed to get audio channel", flush=True)
                return

            print("[AudioStream] Audio playback started successfully", flush=True)

            while channel.get_busy() and not self._stop_event.is_set() and self.is_streaming:
                if self.is_paused:
                    channel.pause()
                    print("[AudioStream] Channel paused", flush=True)
                    while self.is_paused and not self._stop_event.is_set():
                        time.sleep(0.1)
                    if not self._stop_event.is_set() and self.is_streaming:
                        channel.unpause()
                        print("[AudioStream] Channel unpaused", flush=True)

                pygame.time.wait(100)

            print("[AudioStream] Audio playback finished", flush=True)

        except pygame.error as exc:
            print(f"[AudioStream] Pygame error streaming audio '{audio_file_path}': {exc}", flush=True)
        except Exception as exc:
            print(f"[AudioStream] Error streaming audio '{audio_file_path}': {exc}", flush=True)
        finally:
            self.is_streaming = False
            self.is_paused = False

    def pause_stream(self) -> None:
        if self.is_streaming and not self.is_paused:
            self.is_paused = True
            self.pause_time = time.time()
            print("[AudioStream] Audio paused", flush=True)

    def resume_stream(self) -> None:
        if self.is_streaming and self.is_paused:
            self.is_paused = False
            if self.pause_time > 0:
                pause_duration = time.time() - self.pause_time
                self.start_time += pause_duration
            print("[AudioStream] Audio resumed", flush=True)

    def stop_stream(self) -> None:
        self.is_streaming = False
        self.is_paused = False
        self._stop_event.set()
        if pygame.mixer.get_init():
            pygame.mixer.stop()

        if self.stream_thread and self.stream_thread.is_alive():
            self.stream_thread.join(timeout=1.0)

        self.current_audio_file = None
        self.start_time = 0.0
        self.pause_time = 0.0
        print("[AudioStream] Audio stream stopped", flush=True)

    def set_stream_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(1.0, volume))
        print(f"[AudioStream] Volume set to {self.volume:.2f}", flush=True)

    def get_current_position(self) -> float:
        if not self.is_streaming:
            return 0.0
        if self.is_paused and self.pause_time > 0:
            return self.pause_time - self.start_time
        return time.time() - self.start_time

    def is_stream_playing(self) -> bool:
        return self.is_streaming and not self.is_paused

    def is_stream_paused(self) -> bool:
        return self.is_streaming and self.is_paused

    def get_stream_info(self) -> dict:
        return {
            "file": self.current_audio_file,
            "is_playing": self.is_stream_playing(),
            "is_paused": self.is_stream_paused(),
            "current_position": self.get_current_position(),
            "volume": self.volume,
        }


class MusicManager:
    def __init__(self) -> None:
        self.current_music: str | None = None
        self.is_playing = False
        self.volume = 0.3
        self.music_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def play_music(self, path: str, loop: bool = True) -> None:
        if not os.path.isfile(path):
            print(f"[Music] File not found: {path}", flush=True)
            return

        self.stop_music()
        self._stop_event.clear()
        self.current_music = path
        self.is_playing = True

        if IS_WINDOWS:
            self.music_thread = threading.Thread(
                target=self._play_music_loop,
                args=(path, loop),
                daemon=True,
            )
            self.music_thread.start()

    def _play_music_loop(self, path: str, loop: bool) -> None:
        try:
            _ensure_mixer_initialized()
            while not self._stop_event.is_set() and self.is_playing:
                sound = pygame.mixer.Sound(path)
                sound.set_volume(self.volume)
                channel = sound.play()
                while channel.get_busy() and not self._stop_event.is_set():
                    pygame.time.wait(100)
                if not loop:
                    break
        except Exception as exc:
            print(f"[Music] Error playing music '{path}': {exc}", flush=True)
        finally:
            self.is_playing = False

    def stop_music(self) -> None:
        self.is_playing = False
        self._stop_event.set()
        if self.music_thread and self.music_thread.is_alive():
            self.music_thread.join(timeout=1.0)
        self.current_music = None

    def set_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(1.0, volume))

    def is_music_playing(self) -> bool:
        return self.is_playing


def wrap_raw_audio_as_wav(raw_bytes: bytes, sample_rate: int = 22050) -> io.BytesIO:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(raw_bytes)
    buffer.seek(0)
    return buffer


def play_audio_sync(audio_bytes: bytes) -> None:
    if IS_WINDOWS:
        try:
            _ensure_mixer_initialized()
            if audio_bytes.startswith(b"RIFF"):
                wav_buf = io.BytesIO(audio_bytes)
            else:
                wav_buf = wrap_raw_audio_as_wav(audio_bytes)
            sound = pygame.mixer.Sound(wav_buf)
            channel = sound.play()
            while channel.get_busy():
                pygame.time.wait(10)
        except Exception as exc:
            print(f"[Audio] Pygame playback error: {exc}", flush=True)
    else:
        try:
            if audio_bytes.startswith(b"RIFF"):
                try:
                    wav_buf = io.BytesIO(audio_bytes)
                    with wave.open(wav_buf, "rb") as wav_file:
                        frames = wav_file.getnframes()
                        framerate = wav_file.getframerate()
                        duration = frames / framerate
                        timeout = max(10, int(duration + 5))
                except Exception:
                    estimated_duration = len(audio_bytes) / (48000 * 2)
                    timeout = max(10, int(estimated_duration + 5))
                print(f"[Audio] Playing WAV audio with {timeout}s timeout", flush=True)
                proc = subprocess.Popen(
                    ["timeout", str(timeout), "aplay", "-"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                _, stderr = proc.communicate(input=audio_bytes)
                if proc.returncode not in (0, 124):
                    print(
                        f"[Audio] aplay failed with return code {proc.returncode}: {stderr.decode()}",
                        flush=True,
                    )
            else:
                estimated_duration = len(audio_bytes) / (22050 * 2)
                timeout = max(10, int(estimated_duration + 5))
                print(
                    f"[Audio] Playing PCM audio ({estimated_duration:.1f}s) with {timeout}s timeout",
                    flush=True,
                )
                proc = subprocess.Popen(
                    [
                        "timeout",
                        str(timeout),
                        "aplay",
                        "-R",
                        "400",
                        "-r",
                        "22050",
                        "-f",
                        "S16_LE",
                        "-t",
                        "raw",
                        "-",
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                _, stderr = proc.communicate(input=audio_bytes)
                if proc.returncode not in (0, 124):
                    print(
                        f"[Audio] aplay failed with return code {proc.returncode}: {stderr.decode()}",
                        flush=True,
                    )
        except Exception as exc:
            print(f"[Audio] aplay error: {exc}", flush=True)


_audio_streamer = AudioStreamer()
_music_manager = MusicManager()


def start_audio_stream(audio_file_path: str, start_offset: float = 0.0) -> bool:
    return _audio_streamer.start_stream(audio_file_path, start_offset)


def pause_audio_stream() -> None:
    _audio_streamer.pause_stream()


def resume_audio_stream() -> None:
    _audio_streamer.resume_stream()


def stop_audio_stream() -> None:
    _audio_streamer.stop_stream()


def set_audio_stream_volume(volume: float) -> None:
    _audio_streamer.set_stream_volume(volume)


def get_audio_stream_position() -> float:
    return _audio_streamer.get_current_position()


def is_audio_stream_playing() -> bool:
    return _audio_streamer.is_stream_playing()


def is_audio_stream_paused() -> bool:
    return _audio_streamer.is_stream_paused()


def get_audio_stream_info() -> dict:
    return _audio_streamer.get_stream_info()


def play_music(path: str, loop: bool = True) -> None:
    _music_manager.play_music(path, loop)


def stop_music() -> None:
    _music_manager.stop_music()


def set_music_volume(volume: float) -> None:
    _music_manager.set_volume(volume)


def is_music_playing() -> bool:
    return _music_manager.is_music_playing()


__all__ = [
    "initialize_audio_system",
    "play_sfx",
    "play_music",
    "stop_music",
    "set_music_volume",
    "is_music_playing",
    "start_audio_stream",
    "pause_audio_stream",
    "resume_audio_stream",
    "stop_audio_stream",
    "set_audio_stream_volume",
    "get_audio_stream_position",
    "is_audio_stream_playing",
    "is_audio_stream_paused",
    "get_audio_stream_info",
    "wrap_raw_audio_as_wav",
    "play_audio_sync",
]
