# ProxiTalk Core OS (v2) Architecture

This guide documents `core_os/`, the in-progress rewrite of the ProxiTalk runtime. It's split into two audiences:

- **App developers** — writing apps under the repo-root `apps/`.
- **Backend implementers** — adding a new target platform (a new emulator or new physical device) alongside the existing `emulator_windows` and `device_pi` backends.

> [!NOTE]
> `core_os/` is now the only runtime — the old v1 runtime (`proxitalk.py`, `interfaces.py`, `tts_engines/`, etc.) has been removed. The old `apps/`/`overlays/` trees were moved aside to `old_apps/` and kept only as reference material for porting the remaining ~14 v1 apps into `apps/` (now core_os's own app tree). [Development - Apps](/Development---Apps) describes that retired v1 API for reference during porting; it no longer reflects the running system. Everything below is current.

## Overview

`core_os/` is organized in layers, each only aware of the one below it:

```
apps/                 # The apps themselves (launcher, proxi, ...) — repo root, alongside core_os/.
core_os/
├── core/           # Pure logic + abstract driver contracts. No platform code, no hardware knowledge.
├── backends/       # Concrete driver implementations, one folder per platform (emulator_windows, device_pi).
├── packages/       # Subsystems apps opt into: display_gfx, ui, images, animation, tts, audio, input, storage, language, leds, sleep, apps_registry.
├── apps_runtime/   # Loads apps, builds their scoped context, hosts their lifecycle.
├── devtools/       # Hot-reload watcher used by --dev.
├── bootstrap.py    # Platform-agnostic composition root — wires every layer above together.
├── entry_emulator_windows.py
└── entry_device.py
```

At a high level, one full run looks like this:

1. An **entry point** (`entry_emulator_windows.py` or `entry_device.py`) picks a backend and calls that backend's `compose.build_core_registry()`, which constructs the five hardware drivers (display, input, audio, LEDs, GPIO) for that platform and wraps them in a `CoreRegistry`.
2. The entry point hands that `CoreRegistry` to `bootstrap.run()`, the one platform-agnostic function both entry points share. It builds the `PackageRegistry` (one instance of every discovered package, e.g. `tts`, `ui`, `display_gfx`), then the app-loading machinery (`AppLoader`/`AppControl`), then loads and starts the `launcher` app.
3. From there, a single cooperative **scheduler loop** runs forever: poll for input, dispatch key events to whichever app is focused, call that app's `update()`, repeat — all on one thread, so apps never race with each other or with background work.
4. Apps navigate between each other via `context["app_control"].swap_app(...)`, and each app only sees the packages it declared needing in its `metadata.json`, not a global grab-bag of everything.

The two sections below cover this from each side: what an **app developer** sees (packages, context, widgets) and what a **backend implementer** has to provide (the driver contracts + composition glue) to add a new platform.

## Running it

```bash
# Windows
python core_os/entry_emulator_windows.py [--dev]

# Raspberry Pi (over SSH)
python3 core_os/entry_device.py [--dev]
```

`--dev` restarts the whole process automatically whenever a watched file changes (anything under `core_os/{core,packages,apps_runtime}/`, the repo-root `apps/`, `bootstrap.py`, or the specific backend folder that entry point is using).

---

## For app developers

An app is still a folder under `apps/<app_name>/` with `main.py` + `metadata.json` + icons, and your `App` class still inherits from the same `AppBase` and implements the same lifecycle you already know from [Development - Apps](/Development---Apps):

```python
class App(AppBase):
    def __init__(self, context): ...
    def start(self): ...
    def update(self): ...            # called every tick
    def onkeydown(self, keycode): ...
    def onkeyup(self, keycode): ...
    def stop(self): ...
```

**What's different from v1:** `context` is no longer one giant dict containing everything. It only contains the subsystems ("packages") your app explicitly declares in `metadata.json`, plus a small fixed set of fields every app always gets. Declaring a package you don't need pulls in an unused key; using a package you *didn't* declare fails loudly at load time (`AppLoadError: App '<name>' requires unknown package '<id>'`) rather than silently working sometimes.

### metadata.json

```json
{
  "name": "Proxi",
  "version": "1.0",
  "description": "Flagship TTS communicator for typing and speaking phrases fast.",
  "author": "Pidge",
  "type": "app",
  "cursor_enabled": false,
  "packages": ["display_gfx", "tts", "input", "ui", "language"]
}
```

`packages` is the new field — list every package ID whose API your app wants in `context`. `type` defaults to `"app"` (also used for overlays).

### Universal context fields (always present, no declaration needed)

| Key | What it is |
|---|---|
| `screen_width`, `screen_height` | Display dimensions in pixels |
| `app_path` | Absolute path to your app's own folder |
| `app_control` | Swap/overlay control — see below |

### `context["app_control"]`

Replaces v1's `context["app_manager"]`:

```python
context["app_control"].swap_app(from_app, to_app)          # navigate to another app
context["app_control"].swap_app_async(from_app, to_app, delay=0.0)
context["app_control"].start_overlay(name)                  # e.g. a status bar
context["app_control"].stop_overlay(name)
context["app_control"].is_overlay_running(name)
context["app_control"].list_overlays()
context["app_control"].get_app_instance(name)
```

### Available packages and what they put in `context[package_id]`

Declare only the ones you use.

**`display_gfx`** — drawing primitives, layers, fonts. Owns three composited layers (base/overlay/cursor); draws apply and flush immediately (or on `end_batch()`).
```python
context["display_gfx"]["draw_text"](text, x, y, font=None, fill=255)
context["display_gfx"]["draw_text_inverted"](text, x, y, font=None, padding=1)
context["display_gfx"]["draw_image"](img, x, y)
context["display_gfx"]["draw_area"](x, y, width, height, fill=255)
context["display_gfx"]["invert_area"](x, y, width, height)
context["display_gfx"]["clear_area"](x, y, width, height)
context["display_gfx"]["clear_screen"]()
context["display_gfx"]["draw_overlay_text"](text, x, y, font=None, fill=255)
context["display_gfx"]["draw_overlay_image"](img, x, y)
context["display_gfx"]["draw_overlay_area"](x, y, width, height, fill=255)
context["display_gfx"]["clear_overlay_area"](x, y, width, height)
context["display_gfx"]["begin_batch"]() / ["end_batch"]()
context["display_gfx"]["get_text_size"](text, font=None)     # metric width/height
context["display_gfx"]["measure_ink"](text, font=None)       # tight rendered bbox
context["display_gfx"]["line_height"](text="", font=None)
context["display_gfx"]["wrap_text"](text, width, font=None)
context["display_gfx"]["fonts"]                              # {"small", "default", "large"}
context["display_gfx"]["set_cursor_enabled"](bool) / ["set_cursor_position"](x, y) / ["clear_cursor_area"]()
```

**`ui`** — reusable widgets (built on `display_gfx`, so declare both). Widgets are plain objects your app drives explicitly: forward `onkeydown` to `widget.handle_key(keycode)`, call `.draw()` yourself (or via a layout pass).
```python
context["ui"]["menu"](items, x=0, y=0, width=None, height=None, on_select=None, on_change=None, padding=2, margin=0, border=0, inverted=False)
# on_select fires on Enter; on_change fires on every UP/DOWN move (e.g. to live-update a preview pane — see apps/launcher's icon panel)
context["ui"]["menu_item"](label, value=None, toggled=None)
context["ui"]["text_field"](text_input, x=0, y=0, width=None, font=None, display_transform=None)
context["ui"]["dialog"](title, message, on_yes=None, on_no=None)          # yes/no confirm, drawn on overlay layer
context["ui"]["progress_bar"](x=0, y=0, width=0, height=4)
context["ui"]["toast"]()               # .loading(text) / .message(title, body) / .error(text)
context["ui"]["scroll_panel"](x=0, y=0, width=128, height=64, text="")
context["ui"]["text_box"](text="", font=None, max_lines=None, padding=0, margin=0, border=0, inverted=False)
context["ui"]["screen"](title, body)   # v1's set_screen() pattern
# Layout primitives (avoid hardcoded pixel positions):
context["ui"]["label"](text="", font=None, fill=255, align="start")
context["ui"]["row"](children=None, padding=0, margin=0, spacing=0, inverted=False, border=0)
context["ui"]["column"](children=None, padding=0, margin=0, spacing=0, inverted=False, border=0)
context["ui"]["layout_root"](node, x=None, y=None, width=None, height=None, padding=0, margin=0)
context["ui"]["fill"](widget)      # -> (widget, FILL) tuple for a row/column's children list
context["ui"]["content"](widget)   # -> (widget, CONTENT) tuple
```
All keys are `lower_snake_case`, same as every other package (`context["tts"]["speak_async"]`, etc.) — the widget's own Python class is still `PascalCase` (`Menu`, `TextField`, ...), but that's an internal implementation detail, not the dict key you use from `context`.

`row`/`column`'s `children` param takes a list of `(widget, size)` tuples, where `size` is `FILL`, `CONTENT`, or a fixed pixel count. Rather than writing that tuple by hand, use the `fill`/`content` helpers above:

```python
fill, content = context["ui"]["fill"], context["ui"]["content"]
root = context["ui"]["column"]([content(header), fill(self.field)], margin=2, spacing=2)
context["ui"]["layout_root"](root)
```

A fixed pixel size still just goes in directly as `(widget, 24)` — no helper needed for that case.

**`images`** — load/resize/dither images for the display and draw them, wrapping the same `utils/image_utils.AppImageUtils` v1 apps (`gallery`, `discourse_chat`, `pt_browser`) already use for downloading/dithering. `draw_file`/`draw_url` collapse the "load, resize+dither, blit" dance those apps did by hand into one call; `load_*` stays available when you need to hold onto the prepared image/frames yourself (e.g. animating a GIF, or drawing on the overlay layer).
```python
context["images"]["draw_file"](path, x, y, max_width=None, max_height=None, allow_upscale=False, overlay=False)
context["images"]["draw_url"](url, x, y, max_width=None, max_height=None, allow_upscale=False, overlay=False)
context["images"]["load_file"](path, max_width=None, max_height=None, allow_upscale=False)          # -> {"image", "width", "height"}
context["images"]["load_url"](url, max_width=None, max_height=None, allow_upscale=False)             # -> {"image", "width", "height"}
context["images"]["load_animation_file"](path, max_width=None, max_height=None, allow_upscale=False, min_frame_duration_ms=100)  # -> {"frames", "durations", "width", "height"}
context["images"]["load_animation_url"](url, max_width=None, max_height=None, allow_upscale=False, min_frame_duration_ms=100)
```

**`animation`** — small, explicitly-ticked helpers for simple UI animations (a bare value `Tween`, plus `doslide`/`doscale` convenience wrappers). Nothing here runs on a background thread — drawing is only safe on the single cooperative scheduler thread, so every object returned here must be advanced by calling `.update(dt)` once per frame from your app's own `update()`; if you stop calling it, the animation just stops advancing.
```python
context["animation"]["tween"](from_value, to_value, duration=0.25, easing="ease_out", on_complete=None)
# tween.update(dt); tween.value; tween.done — from_value/to_value can be a number or an (x, y, ...) tuple

context["animation"]["doslide"](widget, from_x=None, from_y=None, duration=0.25, easing="ease_out")
# animates any widget with .x/.y/.draw() from an off-screen (from_x, from_y) to wherever it's
# ALREADY positioned (its .x/.y at construction time) — position it/run layout_root FIRST, then wrap it

context["animation"]["doscale"](path, center_x, center_y, target_size, duration=0.25, easing="ease_out", start_size=2)
# draws an image centered at (center_x, center_y), growing from start_size to target_size px square —
# re-decodes the image via images.draw_file every frame, so check frame timing before using on anything
# bigger than a small icon

context["animation"]["linear"], context["animation"]["ease_in"], context["animation"]["ease_out"], context["animation"]["ease_in_out"]
# easing curves as plain callables — pass one of these, or its string name ("ease_out" etc.), to any of the above
```
See `apps/launcher/main.py`'s icon panel for a worked example: `Menu.on_change` fires whenever the highlighted row moves, which rebuilds a `doslide` that animates the newly-selected app's icon in from the right edge of the display each time.

**`tts`** — text-to-speech.
```python
context["tts"]["speak_async"](text, on_done=None, on_error=None, play=True)   # non-blocking, no manual thread needed
context["tts"]["synthesize"](text)                 # -> audio bytes, blocking
context["tts"]["set_engine"](engine_id) / ["get_engine"]()
context["tts"]["get_available_engines"]() / ["get_all_engines"]() / ["get_disabled_engines"]()
context["tts"]["describe_engines"]() / ["get_engine_capabilities"](engine_id)
```

**`audio`** — sound effects, music, streaming.
```python
context["audio"]["play_sfx"](path)                 # one-shot WAV playback
context["audio"]["play_music"](path, loop=True) / ["stop_music"]() / ["set_music_volume"](v) / ["is_music_playing"]()
context["audio"]["start_stream"](path, start_offset=0.0) / ["pause_stream"]() / ["resume_stream"]() / ["stop_stream"]()
context["audio"]["set_stream_volume"](v) / ["get_stream_position"]() / ["is_stream_playing"]() / ["is_stream_paused"]() / ["get_stream_info"]()
```

**`input`** — keymap helpers + text entry.
```python
context["input"]["key_map"] / ["shift_key_map"]
context["input"]["apply_shift_mapping"](keycode, shift_pressed)
context["input"]["make_text_input"](autocomplete_path=None, japanese_path=None, max_length=200, is_japanese_fn=None)
```

**`storage`** — user preferences (re-exposes `UserPreferences`' own `get_*`/`set_*`/`is_*`/`toggle_*` methods directly).
```python
context["storage"]["preferences"]        # the UserPreferences instance itself
context["storage"]["get_auto_sleep_minutes"]()   # example — any public UserPreferences method is available by name
```

**`language`** — system-wide English/Japanese setting; also drives romaji→kana IME preview.
```python
context["language"]["get_language"]() / ["set_language"](lang) / ["toggle_language"]()
context["language"]["is_japanese"]()
context["language"]["t"](key, default=None)                 # translated UI string lookup
context["language"]["romaji_preview"](buffer)                # live as-you-type kana conversion
context["language"]["to_speech_text"](text)                  # final conversion before speaking
context["language"]["available_languages"]()
```

Translated strings live in your own app folder, not in the `language` package — drop a `strings.json` next to `metadata.json`:
```json
{
  "apps.my_app": {"en": "My App", "ja": "マイアプリ"},
  "my_app.some_label": {"en": "Some Label", "ja": "..."}
}
```
Keys are dotted `"<app_name>.<thing>"` by convention (plus `"apps.<app_name>"` for the name shown in the launcher/app_settings lists) so an unused key is traceable back to your app. The `language` package auto-discovers every `apps/*/strings.json` at startup and merges them — no central file to edit, and `scaffold_app.py` generates a starter one for you.

**`leds`** — RGB LED effects (new in v2; v1 never exposed these to apps).
```python
context["leds"]["set_solid"](r, g, b, brightness=8) / ["set_pixel"](index, r, g, b, brightness=8) / ["off"]()
context["leds"]["blink"](r, g, b, interval_s=0.3, count=None)
context["leds"]["chase"](colors, step_interval_s=0.3)
```

**`sleep`** — idle-timeout suspend/resume. Apps rarely call this directly (bootstrap wires it to input activity); it's here in case you need to check or force state.
```python
context["sleep"]["is_sleeping"]() / ["enter_sleep"]() / ["exit_sleep"]() / ["set_idle_timeout"](seconds)
```

**`apps_registry`** — enumerates all apps under `apps/` (what the launcher uses).
```python
context["apps_registry"]["all"]              # list of {"name", "path", "metadata"}
context["apps_registry"]["by_name"]          # dict keyed by folder name
context["apps_registry"]["load_icon"](app_identifier, state=None)   # state: None, "selected", etc.
context["apps_registry"]["refresh"]()
```

### Testing your app

Same workflow as v1: run the emulator entry point, use `WASD`/arrow keys + Enter/Esc to navigate to your app in the launcher, and pass `--dev` to auto-restart on save. See [Development - Apps](/Development---Apps) for general input/graphics conventions (128x64, 1-bit color, PIL-based drawing) — those are unchanged in v2.

---

## For backend implementers (new emulator or new device)

A "backend" is a folder under `core_os/backends/<name>/` providing concrete driver implementations plus one `compose.py` and one `config/paths.py`. The rule that makes this safe to add without touching anything else: **`core/` never imports platform-specific code, and no backend imports another backend.** The only things every backend shares are the abstract contracts in `core/drivers/base.py` and the pure logic in `core/scheduler.py`/`core/event_bus.py`.

### 1. Implement the five driver contracts (`core_os/core/drivers/base.py`)

```python
class DisplayDriver(ABC):
    width: int; height: int
    def fill(self, color: int) -> None: ...      # 0 = off, nonzero = on
    def image(self, img) -> None: ...             # blit a PIL Image, mode '1'
    def show(self) -> None: ...                   # flush to the physical panel
    def contrast(self, level: int) -> None: ...   # 0-255
    def invert(self, flag: bool) -> None: ...     # optional, default no-op
    def stop(self) -> None: ...

class InputDriver(ABC):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def poll(self, timeout: float = 0.0) -> List[InputEvent]: ...  # queued events, wait up to timeout
    def is_ready(self) -> bool: ...               # optional, default True

class AudioOutputDriver(ABC):
    def play_pcm(self, pcm_bytes: bytes, sample_rate: int, blocking: bool = False) -> None: ...
    def play_file(self, path: str, blocking: bool = False) -> None: ...
    def stop(self) -> None: ...
    def set_volume(self, volume: float) -> None: ...   # optional, default no-op

class LedDriver(ABC):
    num_leds: int = 0
    def set_pixels(self, pixels: List[tuple], brightness: int = 8) -> None: ...
    def clear(self) -> None: ...
    def stop(self) -> None: ...

class GpioDriver(ABC):
    def setup_output(self, pin: int) -> None: ...
    def setup_input(self, pin: int, pull_up: bool = True) -> None: ...
    def write(self, pin: int, high: bool) -> None: ...
    def read(self, pin: int) -> bool: ...
    def cleanup(self) -> None: ...
```

`InputEvent` is `dataclass(kind: "key"|"status", keycode=None, keystate=None, data=None, timestamp=0.0)`. Emit `kind="key"` events (with `keystate` as `KEY_DOWN`/`KEY_UP` from `core/drivers/base.py`) for keypresses, and `kind="status"` (with `data` like `"connected"`/`"disconnected"`) for connection changes — bootstrap turns those into `input_<data>` broadcasts.

If you don't have real hardware for LEDs/GPIO (as with the Windows emulator), implement a `NullLedDriver`/`NullGpioDriver` that's a harmless no-op — see `backends/emulator_windows/leds.py` / `gpio.py`.

### 2. Write `compose.py`

The one function that knows how to build a full `CoreRegistry` for your platform:

```python
def build_core_registry() -> CoreRegistry:
    return CoreRegistry(
        display=YourDisplayDriver(),
        input=YourInputDriver(),
        audio_output=YourAudioOutputDriver(),
        leds=YourLedDriver(),
        gpio=YourGpioDriver(),
    )
```

### 3. Write `config/paths.py`

Provide the constants `bootstrap.py` reads off `backend_paths`: `CONFIG_DIR`, `FILES_DIR`, `CACHE_DIR`, `FONT_PATH`, `FONT_SMALL_PATH`, `APPS_DIR`, `OVERLAY_DIR`, `AUTOCOMPLETE_PATH`, plus TTS engine paths (`PIPER_BIN`, `MODEL_PATH`, `PIPER_PLUS_MODEL`, `OPENJTALK_HTSVOICE_DIR`) — any that don't apply to your platform can be `None`. Both existing backends are self-contained (they own these values directly rather than importing v1's `config/paths.py`/`config/emulator/paths.py`), and point `APPS_DIR` at the repo-root `apps/` and `OVERLAY_DIR` at `core_os/overlays_v2`.

### 4. Write the entry point

```python
#!/usr/bin/env python3
import os, sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

def main() -> None:
    from core_os import bootstrap
    from core_os.backends.your_backend import compose
    from core_os.backends.your_backend.config import paths

    core = compose.build_core_registry()

    if "--dev" in sys.argv:
        from core_os.devtools.dev_watcher import DevWatcher
        watcher = DevWatcher(
            root=_ROOT,
            apps_dir=paths.APPS_DIR,
            backend_dir=os.path.join(_ROOT, "core_os", "backends", "your_backend"),
        )
        watcher.start()

    bootstrap.run(core, backend_paths=paths, is_windows=False)  # or True

if __name__ == "__main__":
    main()
```

This file should be the **only** place in the whole tree that imports `core_os.backends.your_backend`. That's what guarantees editing your backend can't affect `entry_emulator_windows.py` or `entry_device.py`'s behavior, and vice versa.

### Things you get for free once the drivers exist

You do not need to write any scheduler, event dispatch, package system, or app loading code — `bootstrap.py` wires all of that up identically for every backend from the `CoreRegistry` + `paths` module you provide. In particular, shift-key resolution (raw keycodes only identify the physical key; your `InputDriver` doesn't need to resolve shifted variants itself) and idle-sleep timing are handled centrally in `bootstrap.py`.
