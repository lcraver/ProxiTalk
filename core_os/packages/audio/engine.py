"""Self-contained audio playback engine for core_os — sfx/music/streaming,
independent of the old OS's audio_manager.py. Backends (device_pi,
emulator_windows) and the audio/tts Packages all import this module instead
of reaching into V1 code.
"""

from __future__ import annotations

import io
import os
import platform
import subprocess
import threading
import time
import wave

import pygame

from core_os.core import debug_log

IS_WINDOWS = platform.system() == "Windows"
MIXER_SETTINGS = {"frequency": 22050, "size": -16, "channels": 1}


def _dbg(msg: str, **kwargs) -> None:
    print(msg, **kwargs)


def _ensure_mixer_initialized() -> None:
    """Make sure pygame's mixer is ready before playing audio."""
    try:
        if pygame.mixer.get_init():
            return
    except pygame.error as exc:
        _dbg(f"[Audio] Mixer state check failed: {exc}")
    try:
        pygame.mixer.init(**MIXER_SETTINGS)
        _dbg(
            f"[Audio] Pygame mixer initialized: {MIXER_SETTINGS['frequency']}Hz, 16-bit mono",
            flush=True,
        )
    except pygame.error as exc:
        _dbg(f"[Audio] Failed to initialize pygame mixer: {exc}", flush=True)


def initialize_audio_system() -> None:
    """Public hook to initialize pygame mixer with consistent settings."""
    _ensure_mixer_initialized()


def play_sfx_internal(path: str) -> None:
    if not os.path.isfile(path):
        _dbg(f"[SFX] File not found: {path}", flush=True)
        return

    _dbg(f"[SFX] Playing: {path}", flush=True)
    status_key = f"sfx:{id(threading.current_thread())}"
    debug_log.set_active(status_key, f"[SFX] {os.path.basename(path)}")
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
                _dbg(
                    f"[SFX] aplay failed for '{path}' with return code {proc.returncode}: {stderr.decode()}",
                    flush=True,
                )
    except Exception as exc:
        _dbg(f"[SFX] Error playing wav file '{path}': {exc}", flush=True)
        return
    finally:
        debug_log.clear_active(status_key)
    _dbg(f"[SFX] Finished: {path}", flush=True)


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
        # Bumped by stop_stream() (and so also by every start_stream(), which
        # calls it first) -- any in-flight _stream_audio_loop thread compares
        # its own captured generation against this before actually starting
        # playback, so a stale thread from a call that's since been
        # superseded (e.g. a jog seek immediately followed by quitting the
        # preview) can never call channel.play() after the fact and keep
        # audio going when the caller thinks it already stopped.
        self._generation = 0
        # Raw PCM for the last-loaded file, cached across calls -- jogging
        # (start_stream called repeatedly on the SAME file, just a different
        # start_offset) used to re-decode the whole file from disk on every
        # single arrow press, which is the actual source of the multi-
        # hundred-ms "laggy" feeling; slicing already-decoded bytes is
        # effectively instant.
        self._cached_path: str | None = None
        self._cached_raw: bytes | None = None
        self._cached_frame_size: int = 0
        self._cached_framerate: int = 0

    def _load_raw(self, audio_file_path: str) -> tuple[bytes, int, int]:
        """(raw_pcm, frame_size_bytes, framerate) for `audio_file_path`,
        decoding it via pygame.mixer.Sound (same decoder start_stream
        always used) only if it isn't already cached from the last call."""
        if self._cached_path == audio_file_path and self._cached_raw is not None:
            return self._cached_raw, self._cached_frame_size, self._cached_framerate
        sound = pygame.mixer.Sound(audio_file_path)
        raw = sound.get_raw()
        freq, fmt, channels = pygame.mixer.get_init()
        frame_size = (abs(fmt) // 8) * channels
        self._cached_path = audio_file_path
        self._cached_raw = raw
        self._cached_frame_size = frame_size
        self._cached_framerate = freq
        return raw, frame_size, freq

    def start_stream(self, audio_file_path: str, start_offset: float = 0.0) -> bool:
        if not os.path.isfile(audio_file_path):
            _dbg(f"[AudioStream] File not found: {audio_file_path}", flush=True)
            return False

        try:
            _ensure_mixer_initialized()
            mixer_info = pygame.mixer.get_init()
            _dbg(f"[AudioStream] Pygame mixer settings: {mixer_info}", flush=True)
        except Exception as exc:
            _dbg(f"[AudioStream] Error checking pygame mixer: {exc}", flush=True)
            return False

        _dbg(f"[AudioStream] Starting stream for: {audio_file_path}", flush=True)

        self.stop_stream()  # bumps self._generation, invalidating any thread still in flight
        self._stop_event.clear()
        self.current_audio_file = audio_file_path
        self.is_streaming = True
        self.is_paused = False
        self.start_time = time.time() - start_offset
        self.pause_time = 0.0
        generation = self._generation

        try:
            self.stream_thread = threading.Thread(
                target=self._stream_audio_loop,
                args=(audio_file_path, start_offset, generation),
                daemon=True,
            )
            self.stream_thread.start()
            _dbg("[AudioStream] Stream thread started", flush=True)
            return True
        except Exception as exc:
            _dbg(f"[AudioStream] Error starting stream thread: {exc}", flush=True)
            self.is_streaming = False
            return False

    def _stream_audio_loop(self, audio_file_path: str, start_offset: float, generation: int) -> None:
        try:
            _dbg(f"[AudioStream] Loading audio file: {audio_file_path}", flush=True)
            raw, frame_size, framerate = self._load_raw(audio_file_path)
            if generation != self._generation or self._stop_event.is_set():
                _dbg("[AudioStream] Superseded before playback started, aborting", flush=True)
                return

            # Actual seek -- slice the offset's worth of frames off the
            # front of the decoded PCM and play what's left, rather than
            # always playing the whole file from frame 0 and only
            # pretending (via start_time bookkeeping) that we're further
            # in. frame-aligned so the slice doesn't split a sample and
            # produce a click/glitch at the seek point.
            start_byte = min(len(raw), max(0, int(start_offset * framerate)) * frame_size)
            sliced = raw[start_byte:]
            if not sliced:
                _dbg("[AudioStream] Seek offset past end of file", flush=True)
                return
            sound = pygame.mixer.Sound(buffer=sliced)
            sound.set_volume(self.volume)

            if generation != self._generation or self._stop_event.is_set():
                _dbg("[AudioStream] Superseded before playback started, aborting", flush=True)
                return

            _dbg(f"[AudioStream] Starting playback (offset: {start_offset}s)", flush=True)
            channel = sound.play()
            if not channel:
                _dbg("[AudioStream] Failed to get audio channel", flush=True)
                return

            _dbg("[AudioStream] Audio playback started successfully", flush=True)
            debug_log.set_active("stream", f"[Stream] {os.path.basename(audio_file_path)}")

            while (
                channel.get_busy()
                and not self._stop_event.is_set()
                and self.is_streaming
                and generation == self._generation
            ):
                if self.is_paused:
                    channel.pause()
                    _dbg("[AudioStream] Channel paused", flush=True)
                    debug_log.set_active("stream", f"[Stream] {os.path.basename(audio_file_path)} (paused)")
                    while self.is_paused and not self._stop_event.is_set() and generation == self._generation:
                        time.sleep(0.02)
                    if not self._stop_event.is_set() and self.is_streaming and generation == self._generation:
                        channel.unpause()
                        _dbg("[AudioStream] Channel unpaused", flush=True)
                        debug_log.set_active("stream", f"[Stream] {os.path.basename(audio_file_path)}")

                # 20ms, not 100ms: stop_stream() joins this thread with a
                # timeout, so this poll interval is also roughly how long a
                # seek/quit has to wait for the OLD stream to notice
                # _stop_event and exit before the new one can start -- was
                # a big chunk of jogging's per-press latency.
                pygame.time.wait(20)

            _dbg("[AudioStream] Audio playback finished", flush=True)

        except pygame.error as exc:
            _dbg(f"[AudioStream] Pygame error streaming audio '{audio_file_path}': {exc}", flush=True)
        except Exception as exc:
            _dbg(f"[AudioStream] Error streaming audio '{audio_file_path}': {exc}", flush=True)
        finally:
            if generation == self._generation:
                self.is_streaming = False
                self.is_paused = False
                debug_log.clear_active("stream")

    def pause_stream(self) -> None:
        if self.is_streaming and not self.is_paused:
            self.is_paused = True
            self.pause_time = time.time()
            _dbg("[AudioStream] Audio paused", flush=True)

    def resume_stream(self) -> None:
        if self.is_streaming and self.is_paused:
            self.is_paused = False
            if self.pause_time > 0:
                pause_duration = time.time() - self.pause_time
                self.start_time += pause_duration
            _dbg("[AudioStream] Audio resumed", flush=True)

    def stop_stream(self) -> None:
        self.is_streaming = False
        self.is_paused = False
        self._generation += 1
        self._stop_event.set()
        if pygame.mixer.get_init():
            pygame.mixer.stop()

        if self.stream_thread and self.stream_thread.is_alive():
            self.stream_thread.join(timeout=1.0)

        self.current_audio_file = None
        self.start_time = 0.0
        self.pause_time = 0.0
        debug_log.clear_active("stream")
        _dbg("[AudioStream] Audio stream stopped", flush=True)

    def set_stream_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(1.0, volume))
        _dbg(f"[AudioStream] Volume set to {self.volume:.2f}", flush=True)

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
            _dbg(f"[Music] File not found: {path}", flush=True)
            return

        self.stop_music()
        self._stop_event.clear()
        self.current_music = path
        self.is_playing = True
        _dbg(f"[Music] Starting: {path} (loop={loop})", flush=True)

        if IS_WINDOWS:
            self.music_thread = threading.Thread(
                target=self._play_music_loop,
                args=(path, loop),
                daemon=True,
            )
            self.music_thread.start()
        else:
            _dbg("[Music] No non-Windows playback path implemented; not starting thread", flush=True)

    def _play_music_loop(self, path: str, loop: bool) -> None:
        try:
            _ensure_mixer_initialized()
            while not self._stop_event.is_set() and self.is_playing:
                sound = pygame.mixer.Sound(path)
                sound.set_volume(self.volume)
                channel = sound.play()
                _dbg(f"[Music] Playback started: {path}", flush=True)
                debug_log.set_active("music", f"[Music] {os.path.basename(path)}" + (" (loop)" if loop else ""))
                while channel.get_busy() and not self._stop_event.is_set():
                    pygame.time.wait(100)
                if not loop:
                    break
                _dbg(f"[Music] Looping: {path}", flush=True)
        except Exception as exc:
            _dbg(f"[Music] Error playing music '{path}': {exc}", flush=True)
        finally:
            self.is_playing = False
            debug_log.clear_active("music")
            _dbg(f"[Music] Playback loop ended: {path}", flush=True)

    def stop_music(self) -> None:
        was_playing = self.current_music
        self.is_playing = False
        self._stop_event.set()
        if self.music_thread and self.music_thread.is_alive():
            self.music_thread.join(timeout=1.0)
        self.current_music = None
        debug_log.clear_active("music")
        if was_playing:
            _dbg(f"[Music] Stopped: {was_playing}", flush=True)

    def set_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(1.0, volume))
        _dbg(f"[Music] Volume set to {self.volume:.2f}", flush=True)

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
    _dbg(f"[Audio] play_audio_sync: {len(audio_bytes)} bytes, format={'WAV' if audio_bytes.startswith(b'RIFF') else 'raw PCM'}", flush=True)
    debug_log.set_active("audio_sync", "[Audio] Playing synthesized audio")
    try:
        _play_audio_sync_inner(audio_bytes)
    finally:
        debug_log.clear_active("audio_sync")


def _play_audio_sync_inner(audio_bytes: bytes) -> None:
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
            _dbg("[Audio] play_audio_sync finished", flush=True)
        except Exception as exc:
            _dbg(f"[Audio] Pygame playback error: {exc}", flush=True)
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
                _dbg(f"[Audio] Playing WAV audio with {timeout}s timeout", flush=True)
                proc = subprocess.Popen(
                    ["timeout", str(timeout), "aplay", "-"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                _, stderr = proc.communicate(input=audio_bytes)
                if proc.returncode not in (0, 124):
                    _dbg(
                        f"[Audio] aplay failed with return code {proc.returncode}: {stderr.decode()}",
                        flush=True,
                    )
                else:
                    _dbg("[Audio] play_audio_sync finished (WAV)", flush=True)
            else:
                estimated_duration = len(audio_bytes) / (22050 * 2)
                timeout = max(10, int(estimated_duration + 5))
                _dbg(
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
                    _dbg(
                        f"[Audio] aplay failed with return code {proc.returncode}: {stderr.decode()}",
                        flush=True,
                    )
        except Exception as exc:
            _dbg(f"[Audio] aplay error: {exc}", flush=True)


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


def get_audio_duration(audio_file_path: str) -> float:
    """Total length of an audio file in seconds, or 0.0 if it can't be
    read -- loads it as a pygame.mixer.Sound just to measure via
    get_length(), the same decoder AudioStreamer.start_stream() uses to
    actually play it, so whatever formats playback supports here reports
    a real duration too."""
    if not os.path.isfile(audio_file_path):
        return 0.0
    try:
        _ensure_mixer_initialized()
        return pygame.mixer.Sound(audio_file_path).get_length()
    except Exception as exc:
        _dbg(f"[AudioStream] Error reading duration of '{audio_file_path}': {exc}", flush=True)
        return 0.0


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
    "play_sfx_internal",
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
    "get_audio_duration",
]
