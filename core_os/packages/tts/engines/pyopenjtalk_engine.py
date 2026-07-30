from __future__ import annotations

import os
import platform
import threading
import time
import traceback
from typing import Any, Dict, List, Optional

import numpy as np

from .base import EngineResources, TTSEngine

try:
    import pyopenjtalk

    test_result = pyopenjtalk.g2p("test", kana=True)
    PYOPENJTALK_PLUS_AVAILABLE = True
    print("[PyOpenJTalk+] pyopenjtalk-plus module available and working")
except ImportError:
    PYOPENJTALK_PLUS_AVAILABLE = False
    print("[PyOpenJTalk+] Module not available, install with: pip install pyopenjtalk-plus")
except Exception as exc:
    PYOPENJTALK_PLUS_AVAILABLE = False
    print(f"[PyOpenJTalk+] Module available but not working: {exc}")
    if "pathlib" in str(exc).lower() or "windowspath" in str(exc).lower():
        print("[PyOpenJTalk+] Known issue: Windows pathlib compatibility problem")
        print("[PyOpenJTalk+] Workaround: Try on Linux, or wait for package fix")
    else:
        print("[PyOpenJTalk+] This may be due to missing dependencies or other issues")

IS_WINDOWS = platform.system() == "Windows"


class PyOpenJTalkPlusTTS:
    def __init__(self, htsvoice_dir: str, user_preferences=None):
        self.htsvoice_dir = htsvoice_dir
        self.current_voice: Optional[str] = None
        self.available_voices: List[Dict[str, Any]] = []
        self.lock = threading.Lock()
        self.process = None
        self.output_buffer = bytearray()
        self._stop_event = threading.Event()
        self.reader_thread: Optional[threading.Thread] = None
        self._request_id = 0
        self.user_preferences = user_preferences

        if not PYOPENJTALK_PLUS_AVAILABLE:
            print("[PyOpenJTalk+] Error: pyopenjtalk-plus not available")
            print("[PyOpenJTalk+] Install with: pip install pyopenjtalk-plus")
            return

        self._discover_voices()
        self._set_default_voice()

        try:
            result = pyopenjtalk.g2p("テスト", kana=True)
            print(f"[PyOpenJTalk+] Module test successful: {result}")
        except Exception as exc:
            print(f"[PyOpenJTalk+] Module test failed: {exc}")
            print("[PyOpenJTalk+] Note: pyopenjtalk-plus may have dependency issues on this system")

        self.start_process()

    def start_process(self) -> None:
        import subprocess
        import sys
        import tempfile

        self._stop_event.clear()
        self.output_buffer = bytearray()

        try:
            server_script = '''
import sys
import json
import numpy as np
import traceback
import tempfile
import wave
import os
import signal
import time
import threading

class SynthesisTimeout(Exception):
    pass

def timeout_handler(signum, frame):
    raise SynthesisTimeout("Synthesis timed out")

def synthesis_with_timeout(text, voice_path, timeout_seconds=15):
    result = [None, None, None]

    def synthesis_worker():
        try:
            print(f"Worker: Starting synthesis...", flush=True)
            audio_array, sample_rate = pyopenjtalk.tts(text, speed=1.0, half_tone=0.0)
            result[0] = audio_array
            result[1] = sample_rate
            print(f"Worker: Synthesis complete", flush=True)
        except Exception as e:
            result[2] = str(e)
            print(f"Worker: Synthesis error: {e}", flush=True)

    worker_thread = threading.Thread(target=synthesis_worker, daemon=True)
    worker_thread.start()
    worker_thread.join(timeout=timeout_seconds)

    if worker_thread.is_alive():
        print(f"Worker: Synthesis timeout after {timeout_seconds}s", flush=True)
        raise SynthesisTimeout(f"Synthesis timed out after {timeout_seconds} seconds")

    if result[2]:
        raise Exception(result[2])

    return result[0], result[1]

try:
    import pyopenjtalk
    print("PyOpenJTalk+ synthesis server ready", flush=True)

    if hasattr(signal, 'SIGALRM'):
        signal.signal(signal.SIGALRM, timeout_handler)

    while True:
        try:
            print("Server: Waiting for request...", flush=True)
            line = sys.stdin.readline()
            if not line:
                print("Server: EOF received, shutting down", flush=True)
                break

            print(f"Server: Received request: {line.strip()[:100]}...", flush=True)
            request = json.loads(line.strip())
            request_id = request.get("id", 0)
            text = request.get("text", "")
            voice_path = request.get("voice_path", None)

            print(f"Server: Processing request {request_id} for text: '{text[:50]}...'", flush=True)

            if voice_path:
                print(f"Server: Setting voice to {voice_path}", flush=True)
                pyopenjtalk.DEFAULT_HTS_VOICE = voice_path.encode('utf-8')

            start_time = time.time()

            try:
                audio_array, sample_rate = synthesis_with_timeout(text, voice_path, timeout_seconds=15)
                synthesis_time = time.time() - start_time
                print(f"Server: Synthesis completed in {synthesis_time:.3f}s", flush=True)
            except SynthesisTimeout as e:
                error_response = {
                    "id": request_id,
                    "success": False,
                    "error": "Synthesis timeout",
                    "traceback": str(e)
                }
                print("RESPONSE:" + json.dumps(error_response), flush=True)
                continue

            print(f"Server: Processing audio ({len(audio_array)} samples at {sample_rate}Hz)...", flush=True)

            if audio_array.dtype != np.float64:
                audio_array = audio_array.astype(np.float64)

            audio_max = np.max(np.abs(audio_array))
            if audio_max > 1.0:
                audio_array /= audio_max

            audio_array = np.clip(audio_array * 32767, -32768, 32767).astype(np.int16)

            print(f"Server: Creating WAV file...", flush=True)
            try:
                import platform
                if platform.system() == "Linux":
                    temp_dir = "/tmp" if os.path.exists("/tmp") else None
                else:
                    temp_dir = None

                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False, dir=temp_dir) as temp_wav:
                    temp_wav_path = temp_wav.name

                with wave.open(temp_wav_path, 'wb') as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(sample_rate)
                    wav_file.writeframes(audio_array.tobytes())

                if not os.path.exists(temp_wav_path):
                    raise Exception("WAV file was not created successfully")

                file_size = os.path.getsize(temp_wav_path)
                print(f"Server: WAV file created: {temp_wav_path} ({file_size} bytes)", flush=True)

                total_time = time.time() - start_time
                response = {
                    "id": request_id,
                    "success": True,
                    "wav_path": temp_wav_path,
                    "length": len(audio_array),
                    "sample_rate": sample_rate,
                    "processing_time": total_time
                }
                print("RESPONSE:" + json.dumps(response), flush=True)

            except Exception as wav_error:
                print(f"Server: WAV creation error: {wav_error}", flush=True)
                error_response = {
                    "id": request_id,
                    "success": False,
                    "error": f"WAV creation failed: {str(wav_error)}",
                    "traceback": traceback.format_exc()
                }
                print("RESPONSE:" + json.dumps(error_response), flush=True)

        except Exception as e:
            error_response = {
                "id": request_id,
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }
            print("RESPONSE:" + json.dumps(error_response), flush=True)

except Exception as e:
    print(f"FATAL_ERROR: {str(e)}", flush=True)
    sys.exit(1)
'''

            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp:
                tmp.write(server_script)
                self.server_script_path = tmp.name

            self.process = subprocess.Popen(
                [sys.executable, self.server_script_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=0,
            )

            self.reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
            self.reader_thread.start()
            threading.Thread(target=self._monitor_stderr, daemon=True).start()

            ready = False
            max_wait_iterations = 100 if not IS_WINDOWS else 50
            for i in range(max_wait_iterations):
                if self.process.poll() is not None:
                    print(f"[PyOpenJTalk+] Process died during startup (iteration {i})")
                    try:
                        stderr_output = self.process.stderr.read()
                        if stderr_output:
                            print(f"[PyOpenJTalk+] Process stderr: {stderr_output[:500]}")
                    except Exception:
                        pass
                    break
                time.sleep(0.1)
                buffer_str = self.output_buffer.decode("utf-8", errors="ignore")
                if "PyOpenJTalk+ synthesis server ready" in buffer_str:
                    ready = True
                    print(f"[PyOpenJTalk+] Server ready after {i * 0.1:.1f}s")
                    break

            if ready:
                print("[PyOpenJTalk+] Persistent synthesis process started successfully")
            else:
                print("[PyOpenJTalk+] Warning: Synthesis process may not be ready (Pi needs more time)")
                if not IS_WINDOWS:
                    print("[PyOpenJTalk+] Proceeding anyway on Pi - will use fallback if server fails")

        except Exception as exc:
            print(f"[PyOpenJTalk+] Failed to start persistent process: {exc}")
            self.process = None

    def _read_stdout(self) -> None:
        while not self._stop_event.is_set() and self.process:
            try:
                if self.process.poll() is not None:
                    break
                try:
                    line = self.process.stdout.readline()
                    if line:
                        self.output_buffer.extend(line.encode("utf-8"))
                    else:
                        time.sleep(0.01)
                except Exception as exc:
                    print(f"[PyOpenJTalk+] Output reader readline error: {exc}")
                    time.sleep(0.1)
            except Exception as exc:
                print(f"[PyOpenJTalk+] Output reader error: {exc}")
                break

    def _monitor_stderr(self) -> None:
        while not self._stop_event.is_set() and self.process:
            try:
                if self.process.poll() is not None:
                    break
                line = self.process.stderr.readline()
                if line:
                    line = line.strip()
                    if line:
                        print(f"[PyOpenJTalk+] Server stderr: {line}", flush=True)
                else:
                    time.sleep(0.1)
            except Exception as exc:
                print(f"[PyOpenJTalk+] Stderr monitor error: {exc}")
                break

    def _discover_voices(self) -> None:
        self.available_voices = []
        if not os.path.exists(self.htsvoice_dir):
            print(f"[PyOpenJTalk+] HTS voice directory not found: {self.htsvoice_dir}")
            return
        try:
            for root, _dirs, files in os.walk(self.htsvoice_dir):
                for file in files:
                    if file.endswith(".htsvoice"):
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(root, self.htsvoice_dir)
                        voice_info = {
                            "filename": file,
                            "name": file.replace(".htsvoice", ""),
                            "path": full_path,
                            "category": rel_path if rel_path != "." else "other",
                            "exists": os.path.isfile(full_path),
                        }
                        self.available_voices.append(voice_info)
            self.available_voices.sort(key=lambda x: (x["category"], x["name"]))
            print(f"[PyOpenJTalk+] Discovered {len(self.available_voices)} voice models:")
            for voice in self.available_voices:
                status = " (OK)" if voice["exists"] else " (MISSING)"
                print(f"  - {voice['category']}/{voice['name']}{status}")
        except Exception as exc:
            print(f"[PyOpenJTalk+] Error discovering voices: {exc}")

    # Fallback default when no explicit user preference is set. mei_normal is
    # a well-known, natural-sounding neutral voice among the bundled models.
    DEFAULT_VOICE_NAME = "mei_normal"

    def _set_default_voice(self) -> None:
        if not self.available_voices:
            print("[PyOpenJTalk+] No voices available")
            return
        prefs = self.user_preferences
        if prefs:
            try:
                preferred_voice = prefs.get_pyopenjtalk_voice()
                if preferred_voice:
                    for voice in self.available_voices:
                        if voice["filename"] == preferred_voice and voice["exists"]:
                            self.current_voice = voice["filename"]
                            print(f"[PyOpenJTalk+] Using preferred voice: {voice['name']}")
                            return
            except Exception:
                pass
        for voice in self.available_voices:
            if voice["exists"] and voice["name"] == self.DEFAULT_VOICE_NAME:
                self.current_voice = voice["filename"]
                print(f"[PyOpenJTalk+] Using default voice: {voice['name']}")
                return
        for voice in self.available_voices:
            if voice["exists"]:
                self.current_voice = voice["filename"]
                print(f"[PyOpenJTalk+] Using default voice: {voice['name']}")
                return

    def get_voice_path(self, voice_filename: str) -> Optional[str]:
        for voice in self.available_voices:
            if voice["filename"] == voice_filename:
                return voice["path"]
        return None

    def set_voice(self, voice_filename: str) -> bool:
        voice_path = self.get_voice_path(voice_filename)
        if voice_path and os.path.exists(voice_path):
            old_voice = self.current_voice
            self.current_voice = voice_filename
            print(f"[PyOpenJTalk+] Voice changed to: {voice_filename}")
            if old_voice != voice_filename and self.process:
                print(f"[PyOpenJTalk+] Restarting process for voice change: {old_voice} -> {voice_filename}")
                self.close()
                self.start_process()
            prefs = self.user_preferences
            if prefs:
                try:
                    prefs.set_pyopenjtalk_voice(voice_filename)
                except Exception:
                    pass
            return True
        print(f"[PyOpenJTalk+] Voice not found: {voice_filename}")
        return False

    def get_available_voices(self) -> List[Dict[str, Any]]:
        return self.available_voices

    def get_current_voice(self) -> Optional[str]:
        return self.current_voice

    def get_current_voice_info(self) -> Optional[Dict[str, Any]]:
        for voice in self.available_voices:
            if voice["filename"] == self.current_voice:
                return voice
        return None

    def synthesize(self, text: str, timeout: float = 12.0) -> bytes:
        import json

        with self.lock:
            if not PYOPENJTALK_PLUS_AVAILABLE:
                print("[PyOpenJTalk+] pyopenjtalk-plus not available")
                return b""

            if not self.process or self.process.poll() is not None:
                print("[PyOpenJTalk+] Process not running, restarting...")
                self.start_process()
                if not self.process:
                    print("[PyOpenJTalk+] Failed to restart process, using direct synthesis")
                    voice_path = self.get_voice_path(self.current_voice)
                    return self._synthesize_smart_direct(text, voice_path)

            try:
                voice_path = self.get_voice_path(self.current_voice)
                if voice_path and not os.path.exists(voice_path):
                    print(f"[PyOpenJTalk+] Voice file not found: {self.current_voice}")
                    voice_path = None

                print(f"[PyOpenJTalk+] Synthesizing text: '{text}' with voice: {self.current_voice}")

                self._request_id += 1
                request_id = self._request_id
                request = {
                    "id": request_id,
                    "text": text,
                    "voice_path": str(voice_path) if voice_path else None,
                }

                self.output_buffer.clear()
                request_json = json.dumps(request) + "\n"
                self.process.stdin.write(request_json)
                self.process.stdin.flush()

                synthesis_start = time.time()
                start_time = time.time()
                while time.time() - start_time < timeout:
                    if self.process.poll() is not None:
                        print("[PyOpenJTalk+] Process died during synthesis")
                        voice_path = self.get_voice_path(self.current_voice)
                        return self._synthesize_smart_direct(text, voice_path)

                    buffer_str = self.output_buffer.decode("utf-8", errors="ignore")
                    lines = buffer_str.split("\n")

                    for line in lines:
                        if line.startswith("RESPONSE:"):
                            try:
                                response_data = json.loads(line[9:])
                                if response_data.get("id") == request_id:
                                    if response_data.get("success"):
                                        wav_path = response_data.get("wav_path", "")
                                        sample_rate = response_data.get("sample_rate", 48000)
                                        if wav_path and os.path.exists(wav_path):
                                            with open(wav_path, "rb") as wav_file:
                                                audio_bytes = wav_file.read()
                                            try:
                                                os.unlink(wav_path)
                                            except Exception:
                                                pass

                                            synthesis_time = time.time() - synthesis_start
                                            audio_length_seconds = (len(audio_bytes) - 44) / 2 / sample_rate
                                            realtime_factor = (
                                                audio_length_seconds / synthesis_time if synthesis_time > 0 else 0
                                            )
                                            print(
                                                f"[PyOpenJTalk+] Synthesis completed in {synthesis_time:.3f}s "
                                                f"(RTF: {realtime_factor:.2f}x)"
                                            )
                                            print(
                                                f"[PyOpenJTalk+] Successfully generated WAV file: {len(audio_bytes)} bytes "
                                                f"({audio_length_seconds:.2f}s audio at {sample_rate}Hz)"
                                            )
                                            return audio_bytes
                                        print(f"[PyOpenJTalk+] WAV file not found: {wav_path}")
                                        voice_path = self.get_voice_path(self.current_voice)
                                        return self._synthesize_smart_direct(text, voice_path)
                                    else:
                                        error = response_data.get("error", "Unknown error")
                                        synthesis_time = time.time() - synthesis_start
                                        print(
                                            f"[PyOpenJTalk+] Synthesis error after {synthesis_time:.3f}s: {error}"
                                        )
                                        voice_path = self.get_voice_path(self.current_voice)
                                        return self._synthesize_smart_direct(text, voice_path)
                            except json.JSONDecodeError:
                                continue

                    time.sleep(0.01)

                synthesis_time = time.time() - synthesis_start
                print(f"[PyOpenJTalk+] Synthesis timeout after {timeout} seconds (total time: {synthesis_time:.3f}s)")
                print("[PyOpenJTalk+] Process appears hung, restarting...")
                try:
                    if self.process and self.process.poll() is None:
                        self.process.kill()
                        self.process.wait(timeout=2)
                except Exception:
                    pass
                self.process = None
                self.start_process()
                voice_path = self.get_voice_path(self.current_voice)
                return self._synthesize_smart_direct(text, voice_path)

            except Exception as exc:
                synthesis_time = time.time() - synthesis_start
                print(f"[PyOpenJTalk+] Synthesis error after {synthesis_time:.3f}s: {exc}")
                traceback.print_exc()
                voice_path = self.get_voice_path(self.current_voice)
                return self._synthesize_smart_direct(text, voice_path)

    def close(self) -> None:
        self._stop_event.set()
        if self.process:
            try:
                if self.process.poll() is None:
                    self.process.stdin.write("\n")
                    self.process.stdin.flush()
                self.process.terminate()
                self.process.wait(timeout=3)
            except Exception as exc:
                print(f"[PyOpenJTalk+] Error terminating process: {exc}")
                try:
                    self.process.kill()
                except Exception:
                    pass
        if self.reader_thread and self.reader_thread.is_alive():
            self.reader_thread.join(timeout=1.0)
        if hasattr(self, "server_script_path"):
            try:
                os.unlink(self.server_script_path)
            except Exception:
                pass
        self.process = None
        self.reader_thread = None
        print("[PyOpenJTalk+] Cleanup completed")

    def _synthesize_direct(self, text: str, voice_path: Optional[str]) -> bytes:
        try:
            print("[PyOpenJTalk+] Using direct synthesis fallback")
            if voice_path:
                original_voice = pyopenjtalk.DEFAULT_HTS_VOICE
                pyopenjtalk.DEFAULT_HTS_VOICE = str(voice_path).encode("utf-8")
                try:
                    audio_array, sample_rate = pyopenjtalk.tts(text, speed=1.0, half_tone=0.0)
                finally:
                    pyopenjtalk.DEFAULT_HTS_VOICE = original_voice
            else:
                audio_array, sample_rate = pyopenjtalk.tts(text, speed=1.0, half_tone=0.0)

            if audio_array.dtype != np.float64:
                audio_array = audio_array.astype(np.float64)

            audio_max = np.max(np.abs(audio_array))
            if audio_max > 1.0:
                audio_array = audio_array / audio_max

            audio_array = np.clip(audio_array * 32767, -32768, 32767).astype(np.int16)

            import tempfile
            import wave

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
                temp_wav_path = temp_wav.name

            with wave.open(temp_wav_path, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_array.tobytes())

            with open(temp_wav_path, "rb") as wav_file:
                wav_bytes = wav_file.read()

            try:
                os.unlink(temp_wav_path)
            except Exception:
                pass

            print(f"[PyOpenJTalk+] Direct synthesis: {len(wav_bytes)} bytes at {sample_rate}Hz")
            return wav_bytes
        except Exception as exc:
            print(f"[PyOpenJTalk+] Direct synthesis fallback failed: {exc}")
            return b""

    def _synthesize_smart_direct(self, text: str, voice_path: Optional[str]) -> bytes:
        try:
            print("[PyOpenJTalk+] Using smart direct synthesis")
            if voice_path:
                original_voice = pyopenjtalk.DEFAULT_HTS_VOICE
                pyopenjtalk.DEFAULT_HTS_VOICE = str(voice_path).encode("utf-8")
                try:
                    audio_array, sample_rate = pyopenjtalk.tts(text, speed=1.0, half_tone=0.0)
                finally:
                    pyopenjtalk.DEFAULT_HTS_VOICE = original_voice
            else:
                audio_array, sample_rate = pyopenjtalk.tts(text, speed=1.0, half_tone=0.0)

            if audio_array.dtype != np.float64:
                audio_array = audio_array.astype(np.float64)

            audio_max = np.max(np.abs(audio_array))
            if audio_max > 1.0:
                audio_array /= audio_max

            audio_array = np.clip(audio_array * 32767, -32768, 32767).astype(np.int16)

            import platform as _platform
            import tempfile
            import wave

            if _platform.system() == "Linux":
                temp_dir = "/tmp" if os.path.exists("/tmp") else None
            else:
                temp_dir = None

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False, dir=temp_dir) as temp_wav:
                temp_wav_path = temp_wav.name

            with wave.open(temp_wav_path, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_array.tobytes())

            with open(temp_wav_path, "rb") as wav_file:
                wav_bytes = wav_file.read()

            try:
                os.unlink(temp_wav_path)
            except Exception:
                pass

            print(f"[PyOpenJTalk+] Smart direct synthesis: {len(wav_bytes)} bytes at {sample_rate}Hz")
            return wav_bytes
        except Exception as exc:
            print(f"[PyOpenJTalk+] Smart direct synthesis failed: {exc}")
            return b""


class PyOpenJTalkEngine(TTSEngine):
    engine_id = "openjtalk"
    display_name = "PyOpenJTalk+"
    priority = 30
    capability_tags = {"voices"}

    def __init__(self, resources: EngineResources):
        super().__init__(resources)
        self.instance: Optional[PyOpenJTalkPlusTTS] = None
        self.htsvoice_dir = resources.paths.get("openjtalk_htsvoice_dir")

    @classmethod
    def is_available(cls, resources: EngineResources) -> bool:
        htsvoice_dir = resources.paths.get("openjtalk_htsvoice_dir")
        return PYOPENJTALK_PLUS_AVAILABLE and bool(htsvoice_dir) and os.path.isdir(htsvoice_dir)

    def initialize(self) -> None:
        if not PYOPENJTALK_PLUS_AVAILABLE:
            print("[PyOpenJTalkEngine] pyopenjtalk-plus not available")
            return
        if not self.htsvoice_dir:
            print("[PyOpenJTalkEngine] No HTS voice directory configured")
            return
        self.instance = PyOpenJTalkPlusTTS(self.htsvoice_dir, self.resources.user_preferences)

    def _ensure_instance(self) -> Optional[PyOpenJTalkPlusTTS]:
        if not self.instance:
            self.initialize()
        return self.instance

    def synthesize(self, text: str, timeout: Optional[float] = None) -> bytes:
        instance = self._ensure_instance()
        if not instance:
            return b""
        return instance.synthesize(text, timeout=timeout or 12.0)

    def shutdown(self) -> None:
        if self.instance:
            self.instance.close()
            self.instance = None

    def get_available_voices(self) -> List[Dict[str, Any]]:
        instance = self._ensure_instance()
        return instance.get_available_voices() if instance else []

    def set_voice(self, voice_filename: str) -> bool:
        instance = self._ensure_instance()
        return instance.set_voice(voice_filename) if instance else False

    def get_current_voice(self) -> Optional[str]:
        instance = self._ensure_instance()
        return instance.get_current_voice() if instance else None

    def get_current_voice_info(self) -> Optional[Dict[str, Any]]:
        instance = self._ensure_instance()
        return instance.get_current_voice_info() if instance else None

    # ----- Generic API surface -----
    def get_public_api(self) -> Dict[str, Any]:
        return {
            "list_voices": self.get_available_voices,
            "set_voice": self.set_voice,
            "get_current_voice": self.get_current_voice,
            "get_current_voice_info": self.get_current_voice_info,
        }

    def cache_identity(self) -> Dict[str, Any]:
        current = self.get_current_voice()
        return {"voice": current} if current else {}


AVAILABLE_ENGINES = [PyOpenJTalkEngine]
