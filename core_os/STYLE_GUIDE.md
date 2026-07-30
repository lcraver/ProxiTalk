# core_os Code Style Guide

This documents the naming and structure conventions used throughout `core_os/`. It's PEP 8 plus a handful of project-specific patterns that keep the Package/Driver/Widget systems predictable. Follow it for any new file under `core_os/`.

## Base: PEP 8 naming

| What | Convention | Example |
|---|---|---|
| Module / package (folder) names | `lower_snake_case`, short | `event_bus.py`, `apps_runtime/` |
| Class names | `PascalCase` (acronyms stay upper: `TTSPackage`, not `TtsPackage`) | `CoreRegistry`, `AppHost` |
| Functions / methods / variables | `lower_snake_case` | `read_manifest`, `load_app_instance` |
| Constants | `UPPER_SNAKE_CASE` | `KEY_DOWN`, `AVAILABLE_PACKAGES` |
| "Private" attributes/methods (module-internal, not part of the public API) | single leading underscore | `_registry`, `_flush()`, `_bind_registry()` |
| Module-private helper functions | single leading underscore | `_measure()`, `_draw()` in `layout.py` |

Every public method/function signature gets type hints, including the return type (`-> None` where nothing is returned). Every module starts with:

```python
"""One-paragraph module docstring: what this file is, and — when the
reason isn't obvious from the code — why it's built the way it is."""

from __future__ import annotations
```

`from __future__ import annotations` is mandatory at the top of every `.py` file under `core_os/` (after the module docstring), even in files with no forward references yet — it keeps every file's header shape identical and avoids a class of "works until you add a hint that forward-references itself" bugs later. The only files exempt from a module docstring are trivial ones with no non-obvious behavior to explain (there currently are none — even `entry_device.py` and app `main.py` files carry one).

### Import order

Four groups, each import statement within a group alphabetized, one blank line between groups:

```python
from __future__ import annotations

import os          # 1. stdlib
import time

from typing import Any, Dict

import audio_manager as _am        # 2. third-party / sibling top-level modules (config, utils, interfaces, tts_engines, ...)
from config.keymap import key_map

from core_os.packages.base import Package, PackageResources   # 3. core_os.* imports
from core_os.packages.ui.layout import CONTENT, FILL
```

(`typing` imports are conventionally grouped with stdlib, immediately after plain `import` statements, per the existing files.)

## Project-specific naming patterns

### Packages (`core_os/packages/<id>/package.py`)

- Folder name == `package_id` == the key apps see as `context[package_id]`. Always `lower_snake_case`, one word where possible (`audio`, `tts`, `leds`, `ui`) or `snake_case` for compound ids (`display_gfx`, `apps_registry`).
- The `Package` subclass is named `<PascalCase id>Package` — e.g. `package_id = "display_gfx"` → `DisplayGfxPackage`, `package_id = "tts"` → `TTSPackage` (acronym stays uppercase).
- Every package module ends with `AVAILABLE_PACKAGES = [<TheClass>]` — this is the only thing `packages/loader.py` looks for, so it must be exactly this name.
- `get_public_api()` returns a flat dict; keys are `lower_snake_case` verbs/nouns matching the method they wrap 1:1 (`"speak_async": self.speak_async`), **except** the `ui` package's widget factories — see below.

### Drivers (`core_os/core/drivers/base.py` + `core_os/backends/<backend>/*.py`)

- Abstract contracts are named `<Role>Driver`: `DisplayDriver`, `InputDriver`, `AudioOutputDriver`, `LedDriver`, `GpioDriver`.
- Concrete implementations are named `<Descriptor><Role>Driver` — the descriptor is the underlying tech/library, not the backend folder name: `LumaDisplayDriver`, `MatrixInputDriver`, `AplayAudioOutputDriver`, `Sk9822LedDriver`, `RpiGpioDriver` (device_pi); `EmulatorDisplayDriver`, `EmulatorInputDriver`, `PygameAudioOutputDriver`, `NullLedDriver`, `NullGpioDriver` (emulator_windows). A backend with no real hardware for a contract implements a `Null<Role>Driver` no-op rather than skipping it.
- Every backend's composition function is named `build_core_registry()` — `bootstrap.py` and both entry points call it by that exact name, so a new backend must match it.

### UI widgets (`core_os/packages/ui/`)

The Python **class** for a widget is `PascalCase`, same as any class (`Menu`, `TextField`, `Dialog`, ...). But `get_public_api()` entries are dict keys handed to apps as `context["ui"][key]`, not real Python attribute access — so, like every other package, every key is `lower_snake_case`, matching the `make_<name>` factory method it points to with the `make_` prefix stripped:

| Class (`ui/package.py` or `layout.py`) | Factory method | Public API key |
|---|---|---|
| `Menu` | `make_menu` | `"menu"` |
| `TextField` | `make_text_field` | `"text_field"` |
| `Dialog` | `make_dialog` | `"dialog"` |
| `ProgressBar` | `make_progress_bar` | `"progress_bar"` |
| `Toast` | `make_toast` | `"toast"` |
| `ScrollPanel` | `make_scroll_panel` | `"scroll_panel"` |
| `TextBox` | `make_text_box` | `"text_box"` |
| `Screen` | `make_screen` | `"screen"` |
| `Label` | `make_label` | `"label"` |
| `Image` | `make_image` | `"image"` |
| `Row` | `make_row` | `"row"` |
| `Column` | `make_column` | `"column"` |
| — | `layout_root` | `"layout_root"` |

`menu_item` is the one entry that isn't a factory (`MenuItem` is a plain data holder that doesn't need `gfx` injected, so the class itself is exposed directly), but it keeps the same `lower_snake_case` key shape as everything else. This mirrors every other package's convention exactly (e.g. `tts`'s `"speak_async": self.speak_async`) — there is no PascalCase, camelCase, or UPPER_CASE key anywhere in a package's public API; only the internal Python class names use `PascalCase`, because those are genuine class definitions, not dict keys.

### Building Row/Column children: `fill()` / `content()` helpers

A `Row`/`Column`'s `children` param is a list of `(widget, size)` tuples, where `size` is `FILL`, `CONTENT`, or a fixed pixel count. Writing `(widget, FILL)` by hand at every call site is exactly the kind of boilerplate this style guide exists to avoid repeating, so `context["ui"]["fill"]`/`context["ui"]["content"]` are small helper functions, not raw constants: `fill(widget)` returns `(widget, FILL)`, `content(widget)` returns `(widget, CONTENT)`. A fixed pixel size still just goes in directly as `(widget, 24)` — no helper needed for that case. Prefer these over hand-written tuples in any new app code:

```python
fill, content = self.ui["fill"], self.ui["content"]
root = self.ui["column"]([content(header), fill(self.field)], margin=2, spacing=2)
```

**When adding a new widget**: name the class a `PascalCase` noun, add a `make_<snake_case>` method to `UIPackage` with the exact same base name, and expose it under the identical `lower_snake_case` key (the factory name minus `make_`) in `get_public_api()`. Don't break the pattern by using the class's capitalization for the dict key.

### App context aliases (`apps/*/main.py`)

Apps bind each declared package to a `self.<name>` attribute in `__init__`. Use the package_id itself as the attribute name (`self.tts = context["tts"]`, `self.language = context["language"]`) except `display_gfx`, which both existing apps alias to the shorter, established `self.gfx` — keep using `gfx` for that one specifically rather than introducing a second short name for it.

### Docstrings and comments

- Module docstrings explain **why** the file is built the way it is (a design tradeoff, what it replaces from v1, a non-obvious constraint) — not a restatement of what the code does.
- Inline comments are reserved for the same bar: a subtle invariant, a bug that was fixed and would recur if "simplified" away, or a genuinely non-obvious reason for an ordering/clamp/magic number. Don't add a comment that just restates the next line.

## Applying this guide

If you're adding a new package, driver, or widget and aren't sure what to name something, match the table above exactly rather than improvising a variant — the whole point of these conventions is that once you know the id/class name for one of Package/Driver/Widget, you can predict every other name associated with it without checking.
