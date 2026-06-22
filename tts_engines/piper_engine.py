from __future__ import annotations

import os
import platform
import select
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

from .base import EngineResources, TTSEngine

IS_WINDOWS = platform.system() == "Windows"


if IS_WINDOWS:

    class PersistentPiper:
        def __init__(self, piper_path: str, model_path: str):
            self.piper_path = piper_path
            self.model_path = model_path
            self.process: Optional[subprocess.Popen] = None
            self.lock = threading.Lock()
            self.output_buffer = bytearray()
            self._stop_event = threading.Event()
            self.reader_thread: Optional[threading.Thread] = None
            self.start_process()

        def _read_stdout(self) -> None:
            while not self._stop_event.is_set():
                try:
                    chunk = self.process.stdout.read(1024)
                    if chunk:
                        self.output_buffer.extend(chunk)
                    else:
                        time.sleep(0.01)
                except Exception as exc:
                    print(f"[Piper] stdout read error: {exc}")
                    break

        def _log_stderr(self) -> None:
            for line in iter(self.process.stderr.readline, b""):
                print("Piper stderr:", line.decode(errors="ignore").strip(), flush=True)

        def start_process(self) -> None:
            self._stop_event.clear()
            self.output_buffer = bytearray()
            try:
                self.process = subprocess.Popen(
                    [self.piper_path, "--sentence_silence", "0.1", "--model", self.model_path, "--output-raw"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                    creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
                )
            except Exception as exc:
                print(f"[Piper] Failed to start: {exc}")
                return

            self.reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
            self.reader_thread.start()
            threading.Thread(target=self._log_stderr, daemon=True).start()

        def update_model_path(self, new_model_path: str) -> None:
            self.model_path = new_model_path
            print(f"[Piper] Model path updated to: {os.path.basename(new_model_path)}")
            if self.process:
                self.close()
            self.start_process()

        def synthesize(self, text: str, timeout: float = 5.0) -> bytes:
            with self.lock:
                synthesis_start = time.time()

                if not self.process or self.process.poll() is not None:
                    print("[Piper] Process not running. Restarting.", flush=True)
                    self.start_process()

                self.output_buffer.clear()

                try:
                    self.process.stdin.write(text.encode("utf-8") + b"\n")
                    self.process.stdin.flush()
                except Exception as exc:
                    print(f"[Piper] Failed to send text: {exc}")
                    return b""

                start = time.time()
                while time.time() - start < timeout:
                    if self.output_buffer:
                        time.sleep(0.1)
                        break
                    time.sleep(0.05)

                raw_audio = bytes(self.output_buffer)
                synthesis_time = time.time() - synthesis_start

                if raw_audio:
                    audio_length_seconds = len(raw_audio) / 2 / 22050
                    realtime_factor = audio_length_seconds / synthesis_time if synthesis_time > 0 else 0
                    print(
                        f"[Piper] Synthesis completed in {synthesis_time:.3f}s (RTF: {realtime_factor:.2f}x)"
                    )
                    print(f"[Piper] Audio generated: {len(raw_audio)//2} samples at 22050 Hz")
                else:
                    print(f"[Piper] Synthesis failed after {synthesis_time:.3f}s")

                return raw_audio

        def close(self) -> None:
            self._stop_event.set()
            try:
                if self.process:
                    self.process.stdin.close()
                    self.process.stdout.close()
                    self.process.stderr.close()
                    self.process.terminate()
                    self.process.wait(timeout=2)
            except Exception as exc:
                print(f"[Piper] Cleanup error: {exc}")
            finally:
                self.process = None

else:

    class PersistentPiper:
        def __init__(self, piper_path: str, model_path: str):
            self.piper_path = piper_path
            self.model_path = model_path
            self.process: Optional[subprocess.Popen] = None
            self.lock = threading.Lock()
            self.start_process()

        def _drain_stderr(self) -> None:
            try:
                for line in iter(self.process.stderr.readline, b""):
                    error_msg = line.decode(errors="ignore").strip()
                    if error_msg:
                        print(f"[Piper] stderr: {error_msg}", flush=True)
            except Exception as exc:
                print(f"[Piper] Error reading stderr: {exc}")

        def _check_dependencies(self) -> bool:
            issues: List[str] = []
            if not os.path.exists(self.piper_path):
                issues.append(f"Piper binary not found: {self.piper_path}")
            elif not os.access(self.piper_path, os.X_OK):
                issues.append(f"Piper binary not executable: {self.piper_path}")

            if not os.path.exists(self.model_path):
                issues.append(f"Model file not found: {self.model_path}")
            elif not os.access(self.model_path, os.R_OK):
                issues.append(f"Model file not readable: {self.model_path}")

            if issues:
                print("[Piper] Dependency issues found:")
                for issue in issues:
                    print(f"  - {issue}")
                return False

            print("[Piper] Dependencies check passed")
            return True

        def start_process(self) -> None:
            try:
                print(f"[Piper] Starting process: {self.piper_path}")
                print(f"[Piper] Model path: {self.model_path}")
                print(f"[Piper] Model exists: {os.path.exists(self.model_path)}")
                if not self._check_dependencies():
                    print("[Piper] Dependency check failed, cannot start process", flush=True)
                    return

                self.process = subprocess.Popen(
                    [self.piper_path, "--sentence_silence", "0.1", "--model", self.model_path, "--output-raw"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                )
                print(f"[Piper] Process started successfully with PID: {self.process.pid}")
                threading.Thread(target=self._drain_stderr, daemon=True).start()

                time.sleep(0.1)
                if self.process.poll() is not None:
                    print(f"[Piper] ERROR: Process died immediately with return code: {self.process.poll()}")
                else:
                    print("[Piper] Process appears to be running normally")

            except Exception as exc:
                print(f"[Piper] Failed to start process: {exc}")
                self.process = None

        def update_model_path(self, new_model_path: str) -> None:
            self.model_path = new_model_path
            print(f"[Piper] Model path updated to: {os.path.basename(new_model_path)}")
            if self.process:
                self.close()
            self.start_process()

        def synthesize(self, text: str) -> bytes:
            with self.lock:
                synthesis_start = time.time()

                if not self.process or self.process.poll() is not None:
                    print("[Piper] Process not running. Restarting.")
                    self.start_process()
                    if not self.process:
                        print("[Piper] Failed to restart process")
                        return b""

                try:
                    print(
                        f"[Piper] Sending text to process: '{text[:50]}{'...' if len(text) > 50 else ''}'"
                    )
                    self.process.stdin.write(text.encode("utf-8") + b"\n")
                    self.process.stdin.flush()
                    print("[Piper] Text sent successfully")
                except Exception as exc:
                    print(f"[Piper] Failed to write to Piper: {exc}")
                    print(f"[Piper] Process status: {self.process.poll()}")
                    return b""

                output = b""
                start_time = time.time()
                max_wait = 6.0
                print("[Piper] Waiting for audio output...")

                while time.time() - start_time < max_wait:
                    if self.process.poll() is not None:
                        print(f"[Piper] Process died during synthesis with code: {self.process.poll()}")
                        break
                    if self.process.stdout.closed:
                        print("[Piper] stdout was closed")
                        break
                    try:
                        rlist, _, _ = select.select([self.process.stdout], [], [], 0.1)
                        if rlist:
                            chunk = self.process.stdout.read(1024)
                            if not chunk:
                                print("[Piper] Received empty chunk, breaking")
                                break
                            output += chunk
                            print(f"[Piper] Received {len(chunk)} bytes (total: {len(output)})")
                        elif output:
                            print("[Piper] No more data arriving, stopping")
                            break
                    except Exception as exc:
                        print(f"[Piper] Error during select/read: {exc}")
                        break

                synthesis_time = time.time() - synthesis_start

                if not output:
                    print(f"[Piper] Empty audio after {synthesis_time:.3f}s. Restarting Piper.")
                    self.close()
                    self.start_process()
                    return b""

                audio_length_seconds = len(output) / 2 / 22050
                realtime_factor = audio_length_seconds / synthesis_time if synthesis_time > 0 else 0
                print(
                    f"[Piper] Synthesis completed in {synthesis_time:.3f}s (RTF: {realtime_factor:.2f}x)"
                )
                print(f"[Piper] Audio generated: {len(output)//2} samples at 22050 Hz")

                return output

        def close(self) -> None:
            if self.process:
                try:
                    self.process.stdin.close()
                    self.process.stdout.close()
                    self.process.stderr.close()
                    self.process.terminate()
                    self.process.wait(timeout=1)
                except Exception as exc:
                    print("Error closing Piper:", exc, flush=True)
                finally:
                    self.process = None


class PiperEngine(TTSEngine):
    engine_id = "piper"
    display_name = "Piper"
    priority = 10
    capability_tags = {"models"}

    def __init__(self, resources: EngineResources):
        super().__init__(resources)
        self.instance: Optional[PersistentPiper] = None
        self.available_models: List[Dict[str, Any]] = []
        self.current_model: Optional[str] = None
        self.model_dir = ""
        self.piper_bin = resources.paths.get("piper_bin")
        self.default_model = resources.paths.get("default_piper_model") or resources.paths.get("piper_model")
        if self.default_model:
            self.model_dir = os.path.dirname(self.default_model)

    @classmethod
    def is_available(cls, resources: EngineResources) -> bool:
        bin_path = resources.paths.get("piper_bin")
        return bool(bin_path) and os.path.exists(bin_path)

    def initialize(self) -> None:
        self._discover_models()
        preferred = None
        if self.resources.user_preferences:
            preferred = self.resources.user_preferences.get_piper_model()
        if preferred and os.path.exists(preferred):
            self.current_model = preferred
        elif self.default_model and os.path.exists(self.default_model):
            self.current_model = self.default_model
        elif self.available_models:
            self.current_model = self.available_models[0]["path"]
        else:
            self.current_model = None

        if not self.current_model:
            print("[PiperEngine] No valid models found during initialization")
            return

        self._start_instance(self.current_model)

    def _start_instance(self, model_path: str) -> None:
        if self.instance:
            self.instance.close()
            self.instance = None
        print(f"[PiperEngine] Starting Piper with model: {os.path.basename(model_path)}")
        self.instance = PersistentPiper(self.piper_bin, model_path)

    def synthesize(self, text: str, timeout: Optional[float] = None) -> bytes:
        if not self.instance:
            self.initialize()
        if not self.instance:
            return b""
        if IS_WINDOWS:
            return self.instance.synthesize(text, timeout or 5.0)
        return self.instance.synthesize(text)

    def shutdown(self) -> None:
        if self.instance:
            self.instance.close()
            self.instance = None

    def _discover_models(self) -> None:
        self.available_models = []
        directory = self.model_dir
        if not directory or not os.path.exists(directory):
            print(f"[PiperEngine] Model directory not found: {directory}")
            return
        try:
            for file in os.listdir(directory):
                if file.endswith(".onnx"):
                    full_path = os.path.join(directory, file)
                    self.available_models.append(
                        {
                            "path": full_path,
                            "filename": file,
                            "name": file.replace(".onnx", ""),
                            "exists": os.path.isfile(full_path),
                        }
                    )
            self.available_models.sort(key=lambda item: item["name"])
            print(f"[PiperEngine] Discovered {len(self.available_models)} Piper models")
        except Exception as exc:
            print(f"[PiperEngine] Error discovering models: {exc}")

    # ----- API exposed to manager -----
    def get_models(self) -> List[Dict[str, Any]]:
        return self.available_models

    def get_current_model(self) -> Optional[str]:
        return self.current_model

    def get_current_model_info(self) -> Optional[Dict[str, Any]]:
        if not self.current_model:
            return None
        for model in self.available_models:
            if model["path"] == self.current_model:
                return model
        return {
            "path": self.current_model,
            "filename": os.path.basename(self.current_model),
            "name": os.path.basename(self.current_model).replace(".onnx", ""),
            "exists": os.path.exists(self.current_model),
        }

    def get_active_model_filename(self) -> str:
        if self.current_model:
            return os.path.basename(self.current_model)
        if self.default_model:
            return os.path.basename(self.default_model)
        return "unknown_model"

    def set_model(self, model_path: str) -> bool:
        for model in self.available_models:
            if model_path in {model["path"], model["filename"]}:
                if not model["exists"]:
                    print(f"[PiperEngine] Model file missing: {model['path']}")
                    return False
                self.current_model = model["path"]
                if self.resources.user_preferences:
                    self.resources.user_preferences.set_piper_model(model["path"])
                self._start_instance(model["path"])
                return True
        print(f"[PiperEngine] Model not found: {model_path}")
        return False

    # ----- Generic API surface -----
    def get_public_api(self) -> Dict[str, Any]:
        return {
            "list_models": self.get_models,
            "set_model": self.set_model,
            "get_current_model": self.get_current_model,
            "get_current_model_info": self.get_current_model_info,
            "get_active_model_filename": self.get_active_model_filename,
        }

    def cache_identity(self) -> Dict[str, Any]:
        return {"model": self.get_active_model_filename()}


AVAILABLE_ENGINES = [PiperEngine]
