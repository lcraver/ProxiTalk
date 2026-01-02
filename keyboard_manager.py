import threading
import queue
import time
from dataclasses import dataclass
from typing import Callable, Optional


KEY_DOWN = 1
KEY_UP = 0


@dataclass
class KeyboardEvent:
    """Represents either a key input or a status change."""
    kind: str  # "key" or "status"
    keycode: Optional[str] = None
    keystate: Optional[int] = None
    data: Optional[str] = None
    timestamp: float = 0.0


class KeyboardManager:
    """Background keyboard reader that queues key events for the main loop."""

    def __init__(
        self,
        is_windows: bool,
        display=None,
        win_keycode_map: Optional[dict] = None,
        queue_size: int = 256,
        on_connect: Optional[Callable[[], None]] = None,
        on_disconnect: Optional[Callable[[], None]] = None,
        preferred_device: Optional[str] = None,
    ) -> None:
        self.is_windows = is_windows
        self.display = display
        self.win_keycode_map = win_keycode_map or {}
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self._preferred_device = preferred_device
        self.event_queue: "queue.Queue[KeyboardEvent]" = queue.Queue(maxsize=queue_size)
        self._running = threading.Event()
        self._ready_event = threading.Event()
        self._reader_thread: Optional[threading.Thread] = None
        self._last_status: Optional[str] = None
        self._hook = None
        self._linux_device = None
        self._dropped_events = 0
        self._last_drop_log = 0

    def start(self) -> None:
        if self._reader_thread and self._reader_thread.is_alive():
            return
        self._running.set()
        target = self._windows_loop if self.is_windows else self._linux_loop
        self._reader_thread = threading.Thread(target=target, daemon=True)
        self._reader_thread.start()

    def stop(self) -> None:
        self._running.clear()
        self._release_linux_device()
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)

    def wait_until_ready(self, timeout: Optional[float] = None) -> bool:
        return self._ready_event.wait(timeout=timeout)

    def is_ready(self) -> bool:
        return self._ready_event.is_set()

    def get_event(self, timeout: Optional[float] = None) -> Optional[KeyboardEvent]:
        try:
            return self.event_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _queue_event(self, event: KeyboardEvent) -> None:
        try:
            self.event_queue.put_nowait(event)
        except queue.Full:
            try:
                self.event_queue.get_nowait()
            except queue.Empty:
                pass
            self.event_queue.put_nowait(event)
            self._dropped_events += 1
            if self._dropped_events - self._last_drop_log >= 100:
                print(f"[KeyboardManager] Dropped {self._dropped_events} events so far", flush=True)
                self._last_drop_log = self._dropped_events

    def _release_linux_device(self) -> None:
        if self._linux_device is None:
            return
        try:
            self._linux_device.close()
        except Exception:
            pass
        self._linux_device = None

    def _open_linux_device(self, path, input_device_cls, evdev_module):
        try:
            device = input_device_cls(path)
        except Exception as exc:
            print(f"[KeyboardManager] Failed to open {path}: {exc}", flush=True)
            return None
        return device

    def _update_status(self, status: str) -> None:
        if status == self._last_status:
            return
        self._last_status = status
        if status == "connected":
            self._ready_event.set()
            if self.on_connect:
                self.on_connect()
        elif status == "disconnected":
            self._ready_event.clear()
            if self.on_disconnect:
                self.on_disconnect()
        elif status == "connecting":
            self._ready_event.clear()
        self._queue_event(KeyboardEvent(kind="status", data=status, timestamp=time.time()))

    def _linux_loop(self) -> None:
        try:
            import evdev
            from evdev import InputDevice, categorize, ecodes
        except ImportError:
            self._queue_event(
                KeyboardEvent(
                    kind="status",
                    data="error",
                    timestamp=time.time(),
                )
            )
            return

        reconnect_delay = 2.5
        idle_sleep = 0.005
        self._update_status("connecting")

        while self._running.is_set():
            if self._linux_device is None:
                self._update_status("connecting")
                device = None
                if self._preferred_device:
                    device = self._open_linux_device(self._preferred_device, InputDevice, evdev)
                    if device is None:
                        print(
                            f"[KeyboardManager] Preferred device '{self._preferred_device}' unavailable, falling back to auto-detect",
                            flush=True,
                        )
                if device is None:
                    device = self._find_keyboard(evdev, InputDevice)
                if not device:
                    time.sleep(reconnect_delay)
                    continue
                try:
                    device.set_blocking(False)
                except Exception:
                    pass
                try:
                    device.grab()
                except Exception:
                    pass
                self._linux_device = device
                self._update_status("connected")

            device = self._linux_device
            if device is None:
                continue

            try:
                events = device.read()
                if not events:
                    time.sleep(idle_sleep)
                    continue

                for event in events:
                    if not self._running.is_set():
                        break
                    if event.type != ecodes.EV_KEY:
                        continue
                    key_event = categorize(event)
                    keycode = key_event.keycode
                    if isinstance(keycode, list):
                        keycode = keycode[-1]
                    self._queue_event(
                        KeyboardEvent(
                            kind="key",
                            keycode=keycode,
                            keystate=key_event.keystate,
                            timestamp=time.time(),
                        )
                    )
            except BlockingIOError:
                time.sleep(idle_sleep)
                continue
            except OSError as exc:
                if exc.errno == 19:
                    self._update_status("disconnected")
                    self._release_linux_device()
                    time.sleep(0.25)
                    continue
                self._release_linux_device()
                raise

        self._release_linux_device()

    def _device_has_keyboard_caps(self, device, evdev_module) -> bool:
        """Return True if the device reports basic alphanumeric keys."""
        try:
            key_caps = device.capabilities().get(evdev_module.ecodes.EV_KEY, [])
        except Exception:
            return False

        flat_caps = []
        for entry in key_caps:
            if isinstance(entry, tuple):
                flat_caps.append(entry[0])
            else:
                flat_caps.append(entry)

        required = {evdev_module.ecodes.KEY_A, evdev_module.ecodes.KEY_Z, evdev_module.ecodes.KEY_1}
        return all(code in flat_caps for code in required)

    def _find_keyboard(self, evdev_module, input_device_cls):
        devices = [input_device_cls(path) for path in evdev_module.list_devices()]
        named_keyboards = []
        capability_keyboards = []

        for device in devices:
            name = (device.name or "").lower()
            if self._device_has_keyboard_caps(device, evdev_module):
                if "keyboard" in name:
                    named_keyboards.append(device)
                else:
                    capability_keyboards.append(device)

        if named_keyboards:
            return named_keyboards[0]
        if capability_keyboards:
            return capability_keyboards[0]
        return None

    def _windows_loop(self) -> None:
        try:
            import keyboard
        except ImportError:
            self._queue_event(
                KeyboardEvent(
                    kind="status",
                    data="error",
                    timestamp=time.time(),
                )
            )
            return

        def handler(kb_event):
            if not self._running.is_set():
                return
            if kb_event.event_type not in ("down", "up"):
                return
            keycode = self._map_windows_keycode(kb_event.name)
            if not keycode:
                return
            keystate = KEY_DOWN if kb_event.event_type == "down" else KEY_UP
            self._queue_event(
                KeyboardEvent(
                    kind="key",
                    keycode=keycode,
                    keystate=keystate,
                    timestamp=time.time(),
                )
            )

        self._update_status("connected")
        self._hook = keyboard.hook(handler, suppress=False)
        try:
            while self._running.is_set():
                time.sleep(0.05)
        finally:
            if self._hook is not None:
                keyboard.unhook(self._hook)
                self._hook = None

    def _map_windows_keycode(self, key_name: str) -> str:
        if not key_name:
            return ""
        lookup_key = key_name.lower()
        return self.win_keycode_map.get(lookup_key, key_name.upper())
