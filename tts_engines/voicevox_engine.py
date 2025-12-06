from __future__ import annotations

import json
import os
import platform
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

import requests

from .base import EngineResources, TTSEngine

IS_WINDOWS = platform.system() == "Windows"

class PersistentVoiceVox:
    def __init__(self, voicevox_bin: str, host: str, port: int, speaker_id: int = 2):
        self.voicevox_bin = voicevox_bin
        self.host = host
        self.port = port
        self.speaker_id = speaker_id
        self.base_url = f"http://{host}:{port}"
        self.process: Optional[subprocess.Popen] = None
        self.lock = threading.Lock()
        self.is_running = False
        self.start_process()

    def start_process(self) -> None:
        try:
            print(f"[VoiceVox] Starting VoiceVox engine: {self.voicevox_bin}")
            if not os.path.exists(self.voicevox_bin):
                print(f"[VoiceVox] Binary not found at {self.voicevox_bin}")
                self.is_running = False
                return

            creationflags = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
            self.process = subprocess.Popen(
                [self.voicevox_bin],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            wait_seconds = 3 if IS_WINDOWS else 5
            print(f"[VoiceVox] Waiting {wait_seconds}s for server start...")
            time.sleep(wait_seconds)

            if IS_WINDOWS:
                self.is_running = self._check_server_status()
            else:
                self.is_running = False
                for attempt in range(5):
                    if self._check_server_status():
                        self.is_running = True
                        print(
                            f"[VoiceVox] Engine started successfully at {self.base_url} (attempt {attempt + 1})"
                        )
                        break
                    print(f"[VoiceVox] Server not ready yet, waiting... (attempt {attempt + 1}/5)")
                    time.sleep(2)
                if not self.is_running:
                    print("[VoiceVox] Failed to start engine or server not responding after retries")

            if IS_WINDOWS and self.is_running:
                print(f"[VoiceVox] Engine started successfully at {self.base_url}")
        except Exception as exc:
            print(f"[VoiceVox] Failed to start engine: {exc}")
            self.is_running = False

    def _check_server_status(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/version", timeout=5)
            if response.status_code == 200:
                return True
            print(f"[VoiceVox] Server status failed: HTTP {response.status_code}")
            return False
        except requests.RequestException as exc:
            print(f"[VoiceVox] Server status error: {exc}")
            return False

    def synthesize(self, text: str, timeout: float = 10.0) -> bytes:
        with self.lock:
            synthesis_start = time.time()
            if not self.is_running or not self._check_server_status():
                print("[VoiceVox] Server not running. Restarting.", flush=True)
                self.start_process()
                if not self.is_running:
                    return b""

            try:
                query_response = requests.post(
                    f"{self.base_url}/audio_query",
                    params={"text": text, "speaker": self.speaker_id},
                    timeout=timeout,
                )
                if query_response.status_code != 200:
                    print(f"[VoiceVox] Audio query failed: {query_response.status_code}")
                    return b""

                audio_query = query_response.json()
                synthesis_response = requests.post(
                    f"{self.base_url}/synthesis",
                    headers={"Content-Type": "application/json"},
                    params={"speaker": self.speaker_id},
                    data=json.dumps(audio_query),
                    timeout=timeout,
                )
                if synthesis_response.status_code != 200:
                    print(f"[VoiceVox] Synthesis failed: {synthesis_response.status_code}")
                    return b""

                result = synthesis_response.content
                synthesis_time = time.time() - synthesis_start
                if result:
                    audio_data_size = max(0, len(result) - 44)
                    audio_length_seconds = audio_data_size / 2 / 24000 if audio_data_size else 0
                    realtime_factor = audio_length_seconds / synthesis_time if synthesis_time > 0 else 0
                    print(
                        f"[VoiceVox] Synthesis completed in {synthesis_time:.3f}s (RTF: {realtime_factor:.2f}x)"
                    )
                    print(f"[VoiceVox] Generated {len(result)} bytes ({audio_length_seconds:.2f}s audio)")
                else:
                    print(f"[VoiceVox] Synthesis failed after {synthesis_time:.3f}s")
                return result
            except requests.RequestException as exc:
                print(f"[VoiceVox] Request error: {exc}")
                return b""

    def set_speaker_id(self, speaker_id: int) -> None:
        self.speaker_id = speaker_id
        print(f"[VoiceVox] Speaker ID changed to: {speaker_id}")

    def get_speakers(self) -> List[Dict[str, Any]]:
        try:
            if not self.is_running or not self._check_server_status():
                print("[VoiceVox] Server not running, cannot get speakers")
                return []
            response = requests.get(f"{self.base_url}/speakers", timeout=5)
            if response.status_code == 200:
                speakers_data = response.json()
                speakers: List[Dict[str, Any]] = []
                for speaker in speakers_data:
                    voice_info = {
                        "name": speaker.get("name", "Unknown"),
                        "uuid": speaker.get("speaker_uuid", ""),
                        "version": speaker.get("version", ""),
                        "styles": [],
                    }
                    for style in speaker.get("styles", []):
                        voice_info["styles"].append(
                            {
                                "id": style.get("id", 0),
                                "name": style.get("name", "Normal"),
                                "type": style.get("type", "talk"),
                            }
                        )
                    speakers.append(voice_info)
                return speakers
            print(f"[VoiceVox] Failed to get speakers: {response.status_code}")
            return []
        except Exception as exc:
            print(f"[VoiceVox] Error getting speakers: {exc}")
            return []

    def close(self) -> None:
        self.is_running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except Exception as exc:
                print(f"[VoiceVox] Cleanup error: {exc}")
            finally:
                self.process = None


class VoiceVoxEngine(TTSEngine):
    engine_id = "voicevox"
    display_name = "VoiceVox"
    priority = 20
    capability_tags = {"voices"}

    def __init__(self, resources: EngineResources):
        super().__init__(resources)
        self.instance: Optional[PersistentVoiceVox] = None
        self._speakers_cache: Optional[List[Dict[str, Any]]] = None
        self._speakers_flat_cache: Optional[List[Dict[str, Any]]] = None
        self._cache_timestamp: Optional[float] = None
        self._cache_duration = 300
        self.voicevox_bin = resources.paths.get("voicevox_bin")
        self.voicevox_host = resources.paths.get("voicevox_host", "127.0.0.1")
        self.voicevox_port = int(resources.paths.get("voicevox_port", 50021))
        self._current_speaker_id: int = 2

    @classmethod
    def is_available(cls, resources: EngineResources) -> bool:
        return bool(resources.paths.get("voicevox_bin"))

    def initialize(self) -> None:
        speaker_id = 2
        if self.resources.user_preferences:
            speaker_id = self.resources.user_preferences.get_voicevox_speaker_id()
        self._current_speaker_id = speaker_id
        self.instance = PersistentVoiceVox(
            self.voicevox_bin,
            self.voicevox_host,
            self.voicevox_port,
            speaker_id,
        )

    def synthesize(self, text: str, timeout: Optional[float] = None) -> bytes:
        if not self.instance:
            self.initialize()
        if not self.instance:
            return b""
        voicevox_timeout = timeout or (20.0 if not IS_WINDOWS else 15.0)
        return self.instance.synthesize(text, timeout=voicevox_timeout)

    def shutdown(self) -> None:
        if self.instance:
            self.instance.close()
            self.instance = None

    # ----- Voice cache helpers -----
    def _update_cache(self, speakers: List[Dict[str, Any]]) -> None:
        self._speakers_cache = speakers
        self._cache_timestamp = time.time()
        flat_list: List[Dict[str, Any]] = []
        for voice in speakers:
            for style in voice.get("styles", []):
                flat_list.append(
                    {
                        "id": style.get("id"),
                        "name": f"{voice['name']} ({style['name']})",
                        "voice": voice["name"],
                        "style": style["name"],
                        "type": style.get("type", "talk"),
                    }
                )
        self._speakers_flat_cache = flat_list

    def _cache_valid(self) -> bool:
        if self._cache_timestamp is None:
            return False
        return (time.time() - self._cache_timestamp) < self._cache_duration

    def _ensure_cache(self) -> None:
        if self._cache_valid() and self._speakers_cache:
            return
        if not self.instance:
            self.initialize()
        if not self.instance:
            return
        speakers = self.instance.get_speakers()
        if speakers:
            self._update_cache(speakers)

    # ----- API exposed to manager -----
    def set_speaker_id(self, speaker_id: int) -> None:
        if self.instance:
            self.instance.set_speaker_id(speaker_id)
        self._current_speaker_id = speaker_id
        if self.resources.user_preferences:
            self.resources.user_preferences.set_voicevox_speaker_id(speaker_id)

    def get_current_voice(self) -> Optional[int]:
        if self.instance and self.instance.speaker_id is not None:
            self._current_speaker_id = self.instance.speaker_id
        return self._current_speaker_id

    def get_current_voice_info(self) -> Optional[Dict[str, Any]]:
        current_id = self.get_current_voice()
        if current_id is None:
            return None
        flat_list = self.get_speakers_flat()
        for entry in flat_list:
            if entry.get("id") == current_id:
                return entry
        return None

    def get_speakers(self) -> List[Dict[str, Any]]:
        self._ensure_cache()
        return self._speakers_cache or []

    def get_speakers_flat(self) -> List[Dict[str, Any]]:
        self._ensure_cache()
        return self._speakers_flat_cache or []

    def refresh_speakers_cache(self) -> bool:
        self._cache_timestamp = None
        self._ensure_cache()
        return bool(self._speakers_cache)

    # ----- Generic API surface -----
    def get_public_api(self) -> Dict[str, Any]:
        return {
            "list_voices": self.get_speakers,
            "list_voice_variants": self.get_speakers_flat,
            "refresh_voices": self.refresh_speakers_cache,
            "set_voice": self.set_speaker_id,
            "get_current_voice": self.get_current_voice,
            "get_current_voice_info": self.get_current_voice_info,
        }

    def cache_identity(self) -> Dict[str, Any]:
        current = self.get_current_voice()
        return {"speaker_id": str(current)} if current is not None else {}


AVAILABLE_ENGINES = [VoiceVoxEngine]
