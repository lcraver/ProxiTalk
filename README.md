<img width="1280" height="640" alt="pt social preview" src="https://github.com/user-attachments/assets/3e889d54-46e6-4c2c-ab8c-cf94973eaa69" />

# ProxiTalk
This is the repo for ProxiTalk OS. ProxiTalk is a custom operating system designed for the ProxiTalk "platform", which is a handheld communication and gaming device.

# Apps Included

## Core (`apps/`)

### Launcher
Browse, favorite, and launch every installed experience on the device.

### ![Proxi Icon](apps/proxi/icon.png) Proxi
Flagship TTS communicator for typing and speaking phrases fast.

## Settings (`apps/_Settings/`)

### ![App Settings Icon](apps/_Settings/app_settings/icon.png) App Settings
Toggle app visibility and tweak how entries appear in the launcher.

### ![TTS Settings Icon](apps/_Settings/tts_settings/icon.png) TTS Settings
Pick which engines are active, adjust voices, and tune speech defaults.

### ![WiFi Settings Icon](apps/_Settings/wifi_settings/icon.png) WiFi Settings
Scan for nearby networks and connect directly from the device.

### ![App Reboot Icon](apps/_Settings/reboot/icon.png) App Reboot
Soft-restart the runtime when you need a quick clean slate.

## Internet (`apps/_Internet/`)

### ![Discourse Chat Icon](apps/_Internet/discourse_chat/icon.png) Discourse Chat
Chat with The Garden forums directly from your ProxiTalk handheld.

### ![Browser Icon](apps/_Internet/pt_browser/icon.png) ProxiTalk Browser
Minimalist browser tailored to the 128x64 screen for quick lookups.

## Utilities (`apps/_Utils/`)

### ![Calendar Icon](apps/_Utils/calendar/icon.png) Calendar [WIP]
Proof-of-concept monthly calendar for jotting down upcoming events.

### ![Clock Icon](apps/_Utils/clock/icon.png) Clock
Displays current time/date and offers simple timer capability.

### ![Code Editor Icon](apps/_Utils/code_editor/icon.png) Code Editor
Lightweight editor with syntax highlighting and basic file tools.

### ![Gallery Icon](apps/_Utils/gallery/icon.png) Gallery
Browse monochrome previews of locally stored images.

### ![Git Sync Icon](apps/_Utils/git_sync/icon.png) Git Sync
Check the public repo for updates and sync apps/overlays in place.

### ![Tracker Icon](apps/_Utils/tracker/icon.png) Tracker
4-track, 16-step music tracker with synthesised tones.

### ![Video Player Icon](apps/_Utils/video_player/icon.png) Video Player
Drop in an MP4 and play it back on the ProxiTalk display.

## Games (`apps/_Games/`)

### ![Doom Clone Icon](apps/_Games/doom_clone/icon.png) Doom Clone
Retro raycasting FPS demo lovingly inspired by DOOM.

### ![Tetra Icon](apps/_Games/tetra/icon.png) Tetra
Drop-block puzzle classic adapted to the 1-bit panel.

# Overlays Included

### Life Countdown (Mori)
A life countdown overlay that displays approximate seconds remaining for you to live. Can be turned off in app settings if you want less existential dread.

### Settings
Configure screen brightness, speaker volume, and more without leaving the app you're in.

---

# Configuration & Folder Reference

## Folder Structure

```
ProxiTalk/
├── core_os/        # Runtime (entry points, backends, packages, apps_runtime)
├── apps/           # core_os's own apps (launcher, proxi, ...) — what's actually running
├── old_apps/       # Legacy v1 apps, kept for reference while porting the rest into apps/
├── config/         # Shared configuration files
├── tts/            # TTS engine binaries and voice models
├── assets/         # Fonts and emulator icons (do not modify)
└── files/          # User files: images, videos, etc.
```

> The runtime is `core_os/` plus the repo-root `apps/` tree — see [wiki/Development - Core OS Architecture.md](<wiki/Development - Core OS Architecture.md>) for the current app/backend API. `old_apps/` is the old v1 tree, left in place only as reference material for porting the remaining apps into `apps/`; it is not run by anything anymore.

## Platform Paths

`core_os/` owns its own path config per backend now — `core_os/backends/emulator_windows/config/paths.py` (Windows) and `core_os/backends/device_pi/config/paths.py` (Raspberry Pi) — rather than reading the root `config/paths.py` / `config/emulator/paths.py` below. Those root files are legacy, kept only because the reference-only `apps/`/`overlays/` trees still import them.

When setting up a new install, update the relevant file for your platform. The key paths to set are:

| Variable | What it points to |
|---|---|
| `PIPER_BIN` | Path to the `piper` or `piper.exe` binary |
| `MODEL_PATH` | Default Piper `.onnx` voice model |
| `VOICEVOX_BIN` | Path to the VoiceVox executable (if using VoiceVox) |
| `VOICEVOX_HOST` / `VOICEVOX_PORT` | VoiceVox server address (default `localhost:50021`) |
| `OPENJTALK_HTSVOICE_DIR` | Folder containing OpenJTalk `.htsvoice` files |
| `CACHE_DIR` | Where Piper caches synthesised audio |
| `FILES_DIR` | Where user files (images, video) are stored |

The other paths (`APPS_DIR`, `OVERLAY_DIR`, `ICON_DIR`, `FONT_PATH`, etc.) should follow naturally from your repo root and typically don't need manual edits.

## TTS Voices (`tts/`)

```
tts/
├── piper/          # Piper binary + .onnx voice models
└── openjtalk/      # OpenJTalk .htsvoice files
```

Drop additional Piper `.onnx` model files into `tts/piper/` to make them available in TTS Settings. VoiceVox is an external application that must be installed and running separately.

## User Preferences (`config/user_preferences.json`)

Generated automatically on first run. You can edit it directly or use the in-app settings screens. Key fields:

| Field | Default | Description |
|---|---|---|
| `tts_engine` | `"piper"` | Active TTS engine: `"piper"`, `"voicevox"`, or `"openjtalk"` |
| `disabled_tts_engines` | `[]` | Engines to hide even if installed |
| `piper_model` | `null` | Override the default Piper model path |
| `voicevox_speaker_id` | `2` | VoiceVox speaker/character ID |
| `auto_sleep_minutes` | `5` | Minutes of inactivity before the display sleeps (`0` disables) |
| `pinned_apps` | `[]` | Apps pinned to the top of the launcher |
| `hidden_apps` | `[]` | Apps hidden from the launcher |
| `disabled_overlays` | `[]` | Overlays that should not run |
| `keyboard_device_path` | `null` | Override the keyboard input device path (Linux; e.g. `/dev/input/event0`) |
| `debug_piper_wav` | `false` | Write `.wav` files alongside cached `.raw` audio for debugging |

## Word Map (`config/wordmap.py`)

A Python dict that corrects TTS mispronunciations. Add entries as needed:

```python
word_map = {
    'pidge': 'piddge',   # key: what you type, value: what the TTS pronounces
}
```

## Autocomplete Words (`config/autocomplete_words.txt`)

Plain text file with one word per line, used by the Proxi communicator for autocomplete suggestions. A separate `config/autocomplete_words_japanese.txt` is used when Japanese input is active. Edit either file to add or remove suggestions.

## Discourse Chat Credentials (`config/discourse_login.conf`)

Required if you use the Discourse Chat app. The file is excluded from git — create or edit it with your forum credentials:

```ini
USERNAME=your@email.com
PASSWORD=yourpassword
EMAIL=your@email.com
SESSION_TOKEN=          # optional, leave blank
CHAT_URL=https://your-forum.discourse.group/chat/c/channel-name/ID
```

## User Files (`files/`)

The gallery, video player, and other apps read from this folder. Drop images (`.png`, `.jpg`, `.gif`) and videos (`.mp4`) here to make them available in those apps.

---

# Developer Documentation

## Getting Started

### Prerequisites
- Python 3.7+
- PIL (Pillow) for image processing
- pygame (for Windows emulation)
- keyboard (for Windows input handling)

### Running ProxiTalk
```bash
# Windows
python core_os/entry_emulator_windows.py [--dev]

# Raspberry Pi (over SSH)
python3 core_os/entry_device.py [--dev]
```

On Windows, this will start the emulated display. On the Pi, it runs on actual hardware.

### Startup Audio / Animation
Two optional assets live in the repo root:
- `startup.wav` – plays once through the speaker stack or emulator when the OS boots.
- `startup.gif` – 128×64 (or smaller) monochrome animation that displays while the audio runs.

If you delete either file, that portion of the startup sequence is skipped (no errors are raised). Provide your own versions by dropping replacements with the same filenames in the repo root. Animated GIF frames are automatically centered and dithered, so you can work in grayscale and let the runtime handle the 1‑bit conversion.

## Creating Custom Apps

See [wiki/Development - Core OS Architecture.md](<wiki/Development - Core OS Architecture.md>) for the current app structure, `metadata.json` format, and the full package API (`display_gfx`, `ui`, `tts`, `audio`, `input`, `images`, `animation`, `leds`, `sleep`, `language`, `storage`, `apps_registry`). The tutorial that used to live here (`interfaces.AppBase`, `context["app_manager"]`, `context["drawing"]`, the F1 debug overlay walkthrough) described the old v1 runtime, which has been removed — that API no longer exists in the running system.
