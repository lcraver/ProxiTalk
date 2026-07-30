import os
import platform
import shutil
import subprocess
import threading
import time
from typing import Dict, List, Optional, Set, Tuple

from config.keymap import key_map
from interfaces import AppBase


class App(AppBase):
    """Simple WiFi manager that prefers DietPi/ConnMan but degrades gracefully."""

    STATUS_WRAP = 24
    MAX_PASSPHRASE_LEN = 63
    STATUS_MESSAGE_TTL = 1
    KEYCODE_ALIASES = {
        "KEY_PERIOD": "KEY_DOT",
    }

    def __init__(self, context):
        super().__init__(context)
        self.draw = context["drawing"]
        self.font_small = context["fonts"]["small"]
        self.width = context["screen_width"]
        self.height = context["screen_height"]

        self.is_windows = os.name == "nt"
        self.is_linux = not self.is_windows
        self.is_dietpi = self.is_linux and self._detect_dietpi()
        self.connmanctl = None
        self.nmcli = None
        self.iwlist = None
        self.iwconfig = None
        self.wifi_interface = (
            self.context.get("WIFI_INTERFACE")
            or os.environ.get("PROXITALK_WIFI_IFACE")
            or "wlan0"
        )
        if self.is_linux:
            self.connmanctl = self.context.get("CONNMANCTL_PATH") or self._which_with_fallback(
                "connmanctl",
                ["/usr/bin/connmanctl", "/usr/sbin/connmanctl", "/sbin/connmanctl", "/usr/local/bin/connmanctl"],
            )
            self.nmcli = self.context.get("NMCLI_PATH") or self._which_with_fallback(
                "nmcli",
                ["/usr/bin/nmcli", "/usr/sbin/nmcli", "/sbin/nmcli", "/usr/local/bin/nmcli"],
            )
            self.iwlist = self.context.get("IWLIST_PATH") or self._which_with_fallback(
                "iwlist",
                ["/sbin/iwlist", "/usr/sbin/iwlist", "/usr/bin/iwlist", "/usr/local/sbin/iwlist"],
            )
            self.iwconfig = self.context.get("IWCONFIG_PATH") or self._which_with_fallback(
                "iwconfig",
                ["/sbin/iwconfig", "/usr/sbin/iwconfig", "/usr/bin/iwconfig", "/usr/local/sbin/iwconfig"],
            )

        self.networks: List[Dict[str, object]] = []
        self.selection = -1
        self.scroll_offset = 0
        self.max_visible = 7
        self.needs_redraw = True
        self.status_message = ""
        self.detail_message = ""
        self.status_auto_clear = False
        self.status_timestamp = 0.0
        self.set_status("Press R to scan for WiFi networks.", "", auto_clear=False)

        self.worker_thread: Optional[threading.Thread] = None
        self.worker_task: Optional[str] = None
        self.state_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.defer_scan = False

        self.input_mode: Optional[str] = None
        self.input_buffer = ""
        self.pending_network: Optional[Dict[str, object]] = None
        self.cursor_visible = True
        self.cursor_timer = time.time()

        backend_hint = self._backend_label()
        print(f"[WiFi Settings] Initialized (backend={backend_hint}, dietpi={self.is_dietpi})")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self):
        self.set_status("Scanning for WiFi networks...", "", auto_clear=False)
        self.request_scan(initial=True)

    def stop(self):
        self.stop_event.set()
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=1.0)

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------
    def onkeyup(self, keycode):
        if self.input_mode == "passphrase":
            self.handle_passphrase_input(keycode)
        else:
            self.handle_main_input(keycode)

    def handle_main_input(self, keycode):
        if keycode in ("KEY_DOWN", "KEY_S"):
            self.move_selection(1)
        elif keycode in ("KEY_UP", "KEY_W"):
            self.move_selection(-1)
        elif keycode in ("KEY_ENTER", "KEY_SPACE"):
            self.begin_connect_flow(force_password=False)
        elif keycode == "KEY_P":
            self.begin_connect_flow(force_password=True)
        elif keycode == "KEY_R":
            self.request_scan(initial=False)
        elif keycode in ("KEY_ESC", "KEY_BACKSPACE"):
            self.return_to_launcher()

    def handle_passphrase_input(self, keycode):
        if keycode == "KEY_ESC":
            self._close_input_overlay(message="Passphrase entry canceled.")
            return
        if keycode == "KEY_ENTER":
            if not self.pending_network:
                self._close_input_overlay(message="No network selected.")
                return
            if not self.input_buffer and self.pending_network.get("secure"):
                self.set_status(None, "Passphrase required for secure network.", auto_clear=False)
                return
            network = dict(self.pending_network)
            passphrase = self.input_buffer
            self._close_input_overlay()
            self.request_connection(network, passphrase)
            return
        if keycode == "KEY_BACKSPACE":
            if self.input_buffer:
                self.input_buffer = self.input_buffer[:-1]
                self.needs_redraw = True
            return
        char = self.keycode_to_char(keycode)
        if char and len(self.input_buffer) < self.MAX_PASSPHRASE_LEN:
            self.input_buffer += char
            self.needs_redraw = True

    def move_selection(self, delta):
        with self.state_lock:
            if not self.networks:
                return
            self.selection = (self.selection + delta) % len(self.networks)
            if self.selection < self.scroll_offset:
                self.scroll_offset = self.selection
            elif self.selection >= self.scroll_offset + self.max_visible:
                self.scroll_offset = self.selection - self.max_visible + 1
        self.needs_redraw = True

    def begin_connect_flow(self, force_password: bool):
        network = self.get_selected_network()
        if not network:
            self.set_status(None, "No network selected.", auto_clear=True)
            return
        needs_pass = bool(network.get("secure")) and (force_password or not network.get("favorite"))
        if needs_pass:
            self.open_passphrase_prompt(network)
            return
        self.request_connection(dict(network), passphrase=None)

    def get_selected_network(self) -> Optional[Dict[str, object]]:
        with self.state_lock:
            if not self.networks or self.selection < 0 or self.selection >= len(self.networks):
                return None
            return dict(self.networks[self.selection])

    def open_passphrase_prompt(self, network: Dict[str, object]):
        self.pending_network = dict(network)
        self.input_mode = "passphrase"
        self.input_buffer = ""
        self.cursor_visible = True
        self.cursor_timer = time.time()
        self.set_status(f"Passphrase for {network.get('ssid', 'network')}", "ASCII characters only.", auto_clear=False)
        self.needs_redraw = True

    def _close_input_overlay(self, message: Optional[str] = None):
        self.input_mode = None
        self.pending_network = None
        self.input_buffer = ""
        if message:
            self.set_status(message, "", auto_clear=True)
        self.needs_redraw = True

    def keycode_to_char(self, keycode: str) -> str:
        canonical = self.KEYCODE_ALIASES.get(keycode, keycode)
        return key_map.get(canonical, "")

    def return_to_launcher(self):
        app_manager = self.context.get("app_manager")
        if app_manager:
            app_manager.swap_app_async("wifi_settings", "launcher", update_rate_hz=20.0, delay=0.1)

    # ------------------------------------------------------------------
    # Background work
    # ------------------------------------------------------------------
    def request_scan(self, initial: bool):
        if self.is_worker_active():
            if not initial:
                self.set_status(None, "Operation already running...", auto_clear=True)
            return
        self.worker_task = "scan"
        self.worker_thread = threading.Thread(target=self.scan_worker, daemon=True)
        self.worker_thread.start()
        self.set_status("Scanning for WiFi networks...", "", auto_clear=False)

    def request_connection(self, network: Dict[str, object], passphrase: Optional[str]):
        if self.is_worker_active():
            self.set_status(None, "Please wait for the current action to finish.", auto_clear=True)
            return
        if network.get("secure") and not passphrase and not network.get("favorite"):
            self.set_status(None, "Secure network requires a passphrase.", auto_clear=False)
            return
        self.worker_task = f"connect:{network.get('ssid', 'network')}"
        self.worker_thread = threading.Thread(
            target=self.connect_worker,
            args=(network, passphrase),
            daemon=True,
        )
        self.worker_thread.start()
        self.set_status(f"Connecting to {network.get('ssid', 'network')}...", "", auto_clear=False)

    def scan_worker(self):
        try:
            networks, backend = self.fetch_networks()
            if self.stop_event.is_set():
                return
            with self.state_lock:
                self.networks = networks
                self.selection = 0 if networks else -1
                self.scroll_offset = 0
            count = len(networks)
            if count:
                self.clear_status_messages()
            else:
                self.set_status(
                    "No WiFi networks detected.",
                    "Check antenna or run R to rescan.",
                    auto_clear=False,
                )
        except Exception as exc:  # noqa: BLE001
            self.set_status("Scan failed.", self._shorten_error(exc), auto_clear=False)
            print(f"[WiFi Settings] Scan error: {exc}")
        finally:
            self.worker_task = None
            self.worker_thread = None
            self.needs_redraw = True

    def connect_worker(self, network: Dict[str, object], passphrase: Optional[str]):
        try:
            success, message = self.perform_connection(network, passphrase)
            if success:
                self.set_status(message, "", auto_clear=True)
                self.defer_scan = True
            else:
                self.set_status(message, "Connection failed. Check credentials.", auto_clear=False)
        except Exception as exc:  # noqa: BLE001
            self.set_status("Connection error.", self._shorten_error(exc), auto_clear=False)
            print(f"[WiFi Settings] Connect error: {exc}")
        finally:
            self.worker_task = None
            self.worker_thread = None
            self.needs_redraw = True

    def is_worker_active(self) -> bool:
        return bool(self.worker_thread and self.worker_thread.is_alive())

    # ------------------------------------------------------------------
    # Platform helpers
    # ------------------------------------------------------------------
    def fetch_networks(self) -> Tuple[List[Dict[str, object]], str]:
        if self.connmanctl:
            return self.fetch_connman_networks(), "connman"
        if self.nmcli:
            return self.fetch_nmcli_networks(), "nmcli"
        if self.iwlist:
            return self.fetch_iwlist_networks(), "iwlist"
        if self.is_windows:
            return self.fetch_stub_networks(), "iwlist"
        return self.fetch_stub_networks(), "fallback"

    def fetch_stub_networks(self) -> List[Dict[str, object]]:
        base = [
            {
                "ssid": "GardenNet",
                "service_id": "stub_garden",
                "strength": 78,
                "security": "WPA2",
                "secure": True,
                "favorite": True,
                "connected": True,
            },
            {
                "ssid": "Workshop",
                "service_id": "stub_work",
                "strength": 64,
                "security": "WPA3",
                "secure": True,
                "favorite": False,
                "connected": False,
            },
            {
                "ssid": "Guest",
                "service_id": "stub_guest",
                "strength": 42,
                "security": "Open",
                "secure": False,
                "favorite": False,
                "connected": False,
            },
            {
                "ssid": "VG_NET",
                "service_id": "stub_vg_net",
                "strength": 42,
                "security": "Open",
                "secure": False,
                "favorite": False,
                "connected": False,
            },
            {
                "ssid": "VG_NET_1",
                "service_id": "stub_vg_net_1",
                "strength": 10,
                "security": "Open",
                "secure": False,
                "favorite": False,
                "connected": False,
            },
            {
                "ssid": "VG_NET_2",
                "service_id": "stub_vg_net_2",
                "strength": 10,
                "security": "Open",
                "secure": False,
                "favorite": False,
                "connected": False,
            },
            {
                "ssid": "VG_NET_5G",
                "service_id": "stub_vg_net_5g",
                "strength": 50,
                "security": "WPA3",
                "secure": True,
                "favorite": False,
                "connected": False,
            },
            {
                "ssid": "WOW_Factor",
                "service_id": "stub_wow_factor",
                "strength": 50,
                "security": "WPA3",
                "secure": True,
                "favorite": False,
                "connected": False,
            }
        ]
        # Nudge strengths so emulator users can see activity.
        jitter = int(time.time()) % 7
        for item in base:
            item["strength"] = max(0, min(100, item["strength"] - 3 + jitter))
        return base

    def fetch_connman_networks(self) -> List[Dict[str, object]]:
        env = self._connman_env()
        subprocess.run([self.connmanctl, "enable", "wifi"], capture_output=True, text=True, env=env, timeout=8)
        subprocess.run([self.connmanctl, "scan", "wifi"], capture_output=True, text=True, env=env, timeout=12)
        result = subprocess.run(
            [self.connmanctl, "services", "--properties"],
            capture_output=True,
            text=True,
            env=env,
            timeout=12,
        )
        if result.returncode != 0:
            raise RuntimeError(self._format_process_error(result))
        return self.parse_connman_services(result.stdout)

    def parse_connman_services(self, raw_text: str) -> List[Dict[str, object]]:
        networks: List[Dict[str, object]] = []
        current: Optional[Dict[str, object]] = None
        for line in raw_text.splitlines():
            if not line.strip():
                continue
            if line[0] not in (" ", "\t"):
                if current and current.get("type") == "wifi":
                    networks.append(self._finalize_connman_service(current))
                current = self._init_connman_service(line)
            elif current is not None:
                self._apply_connman_property(current, line.strip())
        if current and current.get("type") == "wifi":
            networks.append(self._finalize_connman_service(current))
        return self._sort_networks(networks)

    def _init_connman_service(self, header: str) -> Dict[str, object]:
        parts = header.rsplit(" ", 1)
        service_id = parts[-1]
        prefix = parts[0].strip() if len(parts) == 2 else service_id
        tokens = prefix.split(None, 1)
        flags = tokens[0] if tokens else ""
        name = tokens[1] if len(tokens) == 2 else ""
        return {
            "service_id": service_id,
            "flags": flags,
            "name": name.strip(),
            "type": None,
            "security_list": [],
            "strength": 0,
            "favorite": False,
            "state": "",
        }

    def _apply_connman_property(self, target: Dict[str, object], line: str):
        if " = " not in line:
            return
        key, value = line.split(" = ", 1)
        key = key.strip()
        value = value.strip()
        if key == "Type":
            target["type"] = value.lower()
        elif key == "Security":
            target["security_list"] = self._parse_connman_security(value)
        elif key == "Strength":
            try:
                target["strength"] = int(value)
            except ValueError:
                target["strength"] = 0
        elif key == "Favorite":
            target["favorite"] = value.lower() == "true"
        elif key == "State":
            target["state"] = value.lower()

    def _finalize_connman_service(self, data: Dict[str, object]) -> Dict[str, object]:
        ssid = data.get("name") or self._decode_service_id(data.get("service_id", "")) or "<Hidden>"
        security_tokens = data.get("security_list", [])
        strength = max(0, min(100, int(data.get("strength", 0))))
        flags = (data.get("flags") or "").upper()
        state = data.get("state", "")
        connected = "A" in flags or state in ("online", "ready")
        secure = any(token not in ("none", "open", "off") for token in security_tokens)
        return {
            "ssid": ssid,
            "service_id": data.get("service_id", ssid),
            "strength": strength,
            "security": self._describe_security(security_tokens),
            "secure": secure,
            "favorite": bool(data.get("favorite")),
            "connected": connected,
        }

    def _parse_connman_security(self, raw_value: str) -> List[str]:
        value = raw_value.strip()
        if value.startswith("[") and value.endswith("]"):
            value = value[1:-1].strip()
        if not value:
            return []
        return [token.strip().lower() for token in value.split() if token.strip()]

    def _decode_service_id(self, service_id: str) -> str:
        parts = service_id.split("_")
        if len(parts) >= 3:
            hex_name = parts[2]
            try:
                bytes_data = bytes.fromhex(hex_name)
                decoded = bytes_data.decode("utf-8", errors="ignore")
                return decoded or service_id
            except ValueError:
                return service_id
        return service_id

    def _describe_security(self, tokens: List[str]) -> str:
        if not tokens:
            return "Open"
        aliases = {
            "psk": "WPA2",
            "ieee8021x": "802.1X",
            "wep": "WEP",
            "sae": "WPA3",
        }
        labels = [aliases.get(token, token.upper()) for token in tokens]
        return "/".join(labels)

    def _sort_networks(self, networks: List[Dict[str, object]]) -> List[Dict[str, object]]:
        return sorted(
            networks,
            key=lambda item: (
                0 if item.get("connected") else 1,
                0 if item.get("favorite") else 1,
                -int(item.get("strength", 0)),
                str(item.get("ssid", "")).lower(),
            ),
        )

    def fetch_nmcli_networks(self) -> List[Dict[str, object]]:
        env = os.environ.copy()
        env.setdefault("LC_ALL", "C")
        subprocess.run(
            [self.nmcli, "device", "wifi", "rescan"],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        result = subprocess.run(
            [self.nmcli, "-t", "-f", "ACTIVE,SSID,SECURITY,SIGNAL", "device", "wifi"],
            capture_output=True,
            text=True,
            env=env,
            timeout=12,
        )
        if result.returncode != 0:
            raise RuntimeError(self._format_process_error(result))
        networks: List[Dict[str, object]] = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            fields = self._split_nmcli_line(line.strip(), expected=4)
            if len(fields) < 4:
                continue
            active, ssid, security, strength_text = fields
            ssid = ssid or "<Hidden>"
            try:
                strength = int(strength_text)
            except ValueError:
                strength = 0
            secure = security not in ("", "--", "NONE", "none")
            networks.append(
                {
                    "ssid": ssid,
                    "service_id": ssid,
                    "strength": max(0, min(100, strength)),
                    "security": security or ("Open" if not secure else "Unknown"),
                    "secure": secure,
                    "favorite": False,
                    "connected": active.lower() == "yes",
                }
            )
        return self._sort_networks(networks)

    def fetch_iwlist_networks(self) -> List[Dict[str, object]]:
        cmd = self._iwlist_scan_command()
        env = os.environ.copy()
        env.setdefault("LC_ALL", "C")
        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=20)
        if result.returncode != 0:
            raise RuntimeError(self._format_process_error(result))
        networks = self.parse_iwlist_scan(result.stdout)
        connected_ssid = self._read_iwconfig_ssid()
        if connected_ssid:
            for network in networks:
                if network.get("ssid") == connected_ssid:
                    network["connected"] = True
        return self._sort_networks(networks)

    def parse_iwlist_scan(self, raw_text: str) -> List[Dict[str, object]]:
        networks: List[Dict[str, object]] = []
        current: Optional[Dict[str, object]] = None
        for line in raw_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("Cell "):
                if current:
                    networks.append(self._finalize_iwlist_network(current))
                current = {
                    "ssid": "<Hidden>",
                    "address": "",
                    "strength": 0,
                    "secure": False,
                    "security_tokens": set(),
                }
                parts = stripped.split(" - Address:")
                if len(parts) == 2:
                    current["address"] = parts[1].strip()
                continue
            if current is None:
                continue
            if stripped.startswith("ESSID:"):
                essid = stripped[7:].strip().strip('"')
                current["ssid"] = essid or "<Hidden>"
            elif "Quality=" in stripped:
                quality_section = stripped.split("Quality=", 1)[1]
                quality_token = quality_section.split()[0]
                if "/" in quality_token:
                    num_str, denom_str = quality_token.split("/", 1)
                    try:
                        percent = int(float(num_str) / max(float(denom_str), 1.0) * 100)
                        current["strength"] = max(current["strength"], max(0, min(100, percent)))
                    except ValueError:
                        pass
                if "Signal level=" in stripped:
                    dbm_part = stripped.split("Signal level=", 1)[1].split()[0]
                    current["strength"] = max(current["strength"], self._estimate_dbm_strength(dbm_part))
            elif stripped.startswith("Signal level="):
                dbm_part = stripped.split("Signal level=", 1)[1].split()[0]
                current["strength"] = max(current["strength"], self._estimate_dbm_strength(dbm_part))
            elif stripped.startswith("Encryption key:"):
                current["secure"] = stripped.endswith("on")
            elif stripped.startswith("IE:"):
                token = stripped[3:].strip().upper()
                security_tokens: Set[str] = current.get("security_tokens", set())
                if "WPA3" in token or "SAE" in token:
                    security_tokens.add("WPA3")
                elif "WPA2" in token or "802.11I" in token:
                    security_tokens.add("WPA2")
                elif "WPA" in token:
                    security_tokens.add("WPA")
                current["security_tokens"] = security_tokens
            elif stripped.startswith("WEP"):
                security_tokens = current.get("security_tokens", set())
                security_tokens.add("WEP")
                current["security_tokens"] = security_tokens
        if current:
            networks.append(self._finalize_iwlist_network(current))
        return networks

    def _finalize_iwlist_network(self, data: Dict[str, object]) -> Dict[str, object]:
        tokens: Set[str] = data.get("security_tokens", set())
        secure = data.get("secure") or bool(tokens)
        security = "/".join(sorted(tokens)) if tokens else ("Open" if not secure else "Encrypted")
        ssid = data.get("ssid") or "<Hidden>"
        return {
            "ssid": ssid,
            "service_id": data.get("address") or ssid,
            "strength": max(0, min(100, int(data.get("strength", 0)))),
            "security": security,
            "secure": bool(secure),
            "favorite": False,
            "connected": False,
        }

    def perform_connection(self, network: Dict[str, object], passphrase: Optional[str]) -> Tuple[bool, str]:
        if self.connmanctl:
            return self.connect_via_connman(network, passphrase)
        if self.nmcli:
            return self.connect_via_nmcli(network, passphrase)
        if self.iwlist or self.is_windows:
            return False, "Scanning-only backend. Install connman or nmcli to enable connections."
        time.sleep(0.3)
        return True, f"Simulated connection to {network.get('ssid', 'network')} complete."

    def connect_via_connman(self, network: Dict[str, object], passphrase: Optional[str]) -> Tuple[bool, str]:
        env = self._connman_env()
        service_id = network.get("service_id") or network.get("ssid")
        if not service_id:
            raise RuntimeError("Missing service identifier.")
        subprocess.run([self.connmanctl, "enable", "wifi"], capture_output=True, text=True, env=env, timeout=8)
        if passphrase:
            cfg = subprocess.run(
                [self.connmanctl, "config", service_id, "--passphrase", passphrase],
                capture_output=True,
                text=True,
                env=env,
                timeout=12,
            )
            if cfg.returncode != 0:
                raise RuntimeError(self._format_process_error(cfg))
        result = subprocess.run(
            [self.connmanctl, "connect", service_id],
            capture_output=True,
            text=True,
            env=env,
            timeout=20,
        )
        if result.returncode != 0:
            raise RuntimeError(self._format_process_error(result))
        return True, f"Connected to {network.get('ssid', 'network')} via connman."

    def connect_via_nmcli(self, network: Dict[str, object], passphrase: Optional[str]) -> Tuple[bool, str]:
        env = os.environ.copy()
        env.setdefault("LC_ALL", "C")
        ssid = network.get("ssid")
        if not ssid:
            raise RuntimeError("Missing SSID.")
        cmd = [self.nmcli, "device", "wifi", "connect", ssid]
        if passphrase:
            cmd.extend(["password", passphrase])
        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=20)
        if result.returncode != 0:
            raise RuntimeError(self._format_process_error(result))
        return True, f"Connected to {ssid} via nmcli."

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def update(self):
        if self.input_mode == "passphrase":
            now = time.time()
            if now - self.cursor_timer > 0.5:
                self.cursor_visible = not self.cursor_visible
                self.cursor_timer = now
                self.needs_redraw = True
        if self.defer_scan and not self.is_worker_active():
            self.defer_scan = False
            self.request_scan(initial=False)
        if (
            self.worker_task is None
            and self.status_auto_clear
            and (self.status_message or self.detail_message)
            and (time.time() - self.status_timestamp) > self.STATUS_MESSAGE_TTL
        ):
            self.clear_status_messages()
        if self.needs_redraw:
            self.render()

    def render(self):
        with self.state_lock:
            networks = list(self.networks)
            selection = self.selection
            scroll = self.scroll_offset
        self.draw["begin_batch"]()
        self.draw["clear_screen"]()
        self.draw_header(networks)
        self.draw_network_list(networks, selection, scroll)
        self.draw_status()
        self.draw_footer()
        if self.input_mode == "passphrase" and self.pending_network:
            self.draw_passphrase_overlay(self.pending_network)
        self.draw["end_batch"]()
        self.needs_redraw = False

    def draw_header(self, networks: List[Dict[str, object]]):
        self.draw["draw_area"](0, 0, self.width, 6, 255)
        title = "WiFi Settings"
        backend = self._backend_label()
        self.draw["draw_text"](title, 2, 1, self.font_small, 0)
        backend_width = self.context["get_text_size"](backend, self.font_small)[0]
        self.draw["draw_text"](backend, self.width - backend_width - 2, 1, self.font_small, 0)
        current = self._current_connection_name(networks)
        summary = f"Current: {current}" if current else "Current: Offline"
        self.draw["draw_text"](self.truncate_text(summary, 120), 2, 8, self.font_small, 255)

    def draw_network_list(self, networks: List[Dict[str, object]], selection: int, scroll: int):
        area_top = 16
        self.draw["clear_area"](0, area_top, self.width, self.height - area_top - 16)
        if not networks:
            self.draw["draw_text"]("No networks yet.", 2, area_top + 4, self.font_small, 255)
            self.draw["draw_text"]("Press R to rescan.", 2, area_top + 11, self.font_small, 255)
            return
        has_scrollbar = len(networks) > self.max_visible
        visible = networks[scroll: scroll + self.max_visible]
        for idx, network in enumerate(visible):
            row = scroll + idx
            row_y = area_top + idx * 6
            is_selected = row == selection
            text_color = 0 if is_selected else 255
            if is_selected:
                self.draw["draw_area"](0, row_y - 1, self.width, 6, 255)
            name = self.truncate_text(str(network.get("ssid", "?")), 48)
            x = 2
            self.draw["draw_text"](name, x, row_y, self.font_small, text_color)
            signal = self.signal_meter(int(network.get("strength", 0)))
            x += 60 if has_scrollbar else 64
            self.draw["draw_text"](signal, x, row_y, self.font_small, text_color)
            security = network.get("security", "")
            x += 24
            self.draw["draw_text"](self.truncate_text(security, 36), x, row_y, self.font_small, text_color)
        if has_scrollbar:
            self.draw_scrollbar(scroll, len(networks))

    def draw_scrollbar(self, scroll: int, total: int):
        max_scroll = max(1, total - self.max_visible)
        ratio = scroll / max_scroll
        track_top = 15
        track_height = self.height - track_top - 7
        indicator_height = max(6, track_height // 5)
        usable = track_height - indicator_height
        indicator_y = track_top + int(usable * ratio)
        self.draw["draw_area"](self.width - 8, track_top, 8, track_height, 0)
        self.draw["draw_area"](self.width - 4, track_top, 2, track_height, 255)
        self.draw["draw_area"](self.width - 6, indicator_y, 4, indicator_height, 255)

    def draw_status(self):
        if not (self.status_message or self.detail_message):
            return
        status_top = self.height - 18
        status_height = (self.height - 6) - status_top
        self.draw["clear_area"](0, status_top-1, self.width, status_height)
        self.draw["draw_area"](2, status_top, 1, status_height-2, 255)
        status_y = status_top
        for line in self.wrap_text(self.status_message, self.STATUS_WRAP)[:2]:
            self.draw["draw_text"](line, 6, status_y, self.font_small, 255)
            status_y += 6
        if self.detail_message:
            for line in self.wrap_text(self.detail_message, self.STATUS_WRAP)[:2]:
                self.draw["draw_text"](line, 6, status_y, self.font_small, 255)
                status_y += 6

    def draw_footer(self):
        footer_y = self.height - 6
        self.draw["draw_area"](0, footer_y, self.width, 6, 255)
        footer_full = "ENTER connect  R rescan  P pass  ESC back"
        if self.context["get_text_size"](footer_full, self.font_small)[0] <= self.width - 4:
            text = footer_full
        else:
            text = "ENT connect  R scan  ESC back"
        text_width = self.context["get_text_size"](text, self.font_small)[0]
        self.draw["draw_text"](text, max(2, (self.width - text_width) // 2), footer_y + 1, self.font_small, 0)

    def draw_passphrase_overlay(self, network: Dict[str, object]):
        box_w = 120
        box_h = 26
        origin_x = (self.width - box_w) // 2
        origin_y = (self.height - box_h) // 2
        self.draw["draw_area"](origin_x, origin_y, box_w, box_h, 255)
        self.draw["draw_area"](origin_x + 1, origin_y + 1, box_w - 2, box_h - 2, 0)
        title = self.truncate_text(f"{network.get('ssid', 'network')}", 100)
        self.draw["draw_text"](title, origin_x + 3, origin_y + 3, self.font_small, 255)
        masked = "*" * len(self.input_buffer)
        if self.cursor_visible:
            masked += "_"
        masked = self.truncate_text(masked or " ", 100)
        self.draw["draw_text"](masked, origin_x + 3, origin_y + 11, self.font_small, 255)
        helper = "ENTER save  ESC cancel"
        self.draw["draw_text"](helper, origin_x + 3, origin_y + 18, self.font_small, 255)

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------
    def wrap_text(self, text: str, limit: int) -> List[str]:
        if not text:
            return [""]
        words = text.split()
        if not words:
            return [text[:limit]]
        lines: List[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if len(candidate) <= limit:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def truncate_text(self, text: str, max_width: int) -> str:
        measure = self.context["get_text_size"]
        font = self.font_small
        if measure(text, font)[0] <= max_width:
            return text
        ellipsis = "..."
        ellipsis_width = measure(ellipsis, font)[0]
        trimmed = text
        if ellipsis_width > max_width:
            while trimmed and measure(trimmed, font)[0] > max_width:
                trimmed = trimmed[:-1]
            return trimmed
        while trimmed and measure(trimmed + ellipsis, font)[0] > max_width:
            trimmed = trimmed[:-1]
        return (trimmed + ellipsis) if trimmed else ellipsis

    def signal_meter(self, strength: int) -> str:
        clamped = max(0, min(100, strength))
        if clamped >= 80:
            level = 4
        elif clamped >= 60:
            level = 3
        elif clamped >= 40:
            level = 2
        elif clamped >= 20:
            level = 1
        else:
            level = 0
        return f"[{('|' * level) + ('.' * (4 - level))}]"

    def _split_nmcli_line(self, line: str, expected: int) -> List[str]:
        fields: List[str] = []
        buffer = ""
        escape = False
        for char in line:
            if escape:
                buffer += char
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == ":" and len(fields) < expected - 1:
                fields.append(buffer)
                buffer = ""
            else:
                buffer += char
        fields.append(buffer)
        while len(fields) < expected:
            fields.append("")
        return fields

    def _iwlist_scan_command(self) -> List[str]:
        override = self.context.get("IWLIST_CMD")
        if override:
            if isinstance(override, (list, tuple)):
                return list(override)
            if isinstance(override, str):
                return override.split()
        if not self.iwlist:
            raise RuntimeError("iwlist binary not available on this device.")
        interface = self.wifi_interface or "wlan0"
        return [self.iwlist, interface, "scan"]

    def _read_iwconfig_ssid(self) -> Optional[str]:
        override = self.context.get("IWCONFIG_CMD")
        if override:
            if isinstance(override, (list, tuple)):
                cmd = list(override)
            elif isinstance(override, str):
                cmd = override.split()
            else:
                cmd = None
        elif self.iwconfig:
            cmd = [self.iwconfig, self.wifi_interface]
        else:
            cmd = None
        if not cmd:
            return None
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        except Exception:  # noqa: BLE001
            return None
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            if "ESSID:" not in line:
                continue
            essid_part = line.split("ESSID:", 1)[1].strip()
            if essid_part in ("off/any", "\"\""):
                return None
            return essid_part.strip('"')
        return None

    def _estimate_dbm_strength(self, value: str) -> int:
        try:
            cleaned = value.replace("dBm", "")
            level = float(cleaned)
        except ValueError:
            return 0
        # Typical WiFi RSSI is -100 (weak) to -30 (strong). Map to 0-100 scale.
        level = max(-100.0, min(-30.0, level))
        percent = int(((level + 100.0) / 70.0) * 100)
        return max(0, min(100, percent))

    def clear_status_messages(self):
        self.set_status("", "", auto_clear=False)

    def set_status(self, status: Optional[str] = None, detail: Optional[str] = None, auto_clear: bool = True):
        updated = False
        if status is not None:
            self.status_message = status or ""
            updated = True
        if detail is not None:
            self.detail_message = detail or ""
            updated = True
        if not updated:
            return
        has_text = bool(self.status_message or self.detail_message)
        self.status_auto_clear = auto_clear and has_text
        self.status_timestamp = time.time() if self.status_auto_clear else 0.0
        self.needs_redraw = True

    def _backend_label(self) -> str:
        if self.connmanctl:
            return "DietPi/ConnMan"
        if self.nmcli:
            return "nmcli"
        if self.iwlist or self.is_windows:
            return "iwlist"
        return "Stub"

    def _which_with_fallback(self, binary: str, extra_paths: List[str]) -> Optional[str]:
        path = shutil.which(binary)
        if path and os.path.exists(path):
            return path
        for candidate in extra_paths:
            if candidate and os.path.exists(candidate) and os.access(candidate, os.X_OK):
                return candidate
        return None

    def _detect_dietpi(self) -> bool:
        if os.path.exists("/boot/dietpi/.version"):
            return True
        try:
            return "dietpi" in platform.platform().lower()
        except Exception:  # noqa: BLE001
            return False

    def _connman_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        env.setdefault("LC_ALL", "C")
        return env

    def _format_process_error(self, result: subprocess.CompletedProcess) -> str:
        output = (result.stderr or result.stdout or "").strip()
        if not output:
            output = f"Exit code {result.returncode}"
        return output

    def _shorten_error(self, exc: Exception) -> str:
        text = str(exc).strip() or exc.__class__.__name__
        return text[:60] + "..." if len(text) > 60 else text

    def _current_connection_name(self, networks: List[Dict[str, object]]) -> str:
        for network in networks:
            if network.get("connected"):
                return str(network.get("ssid", ""))
        return ""
