import os
import pygame
from assetsLoader import Loader


class btnHandeler:
    def __init__(self):
        self.btn_file_path = Loader("ui/menu").load("btn_config.txt")

        self.key_map = {}
        self.current = {}
        self.previous = {}

        self._last_sync_tick = -1
        self._load_config()

    def _load_config(self):
        special = {
            "ctrl": pygame.K_LCTRL,
            "lctrl": pygame.K_LCTRL,
            "rctrl": pygame.K_RCTRL,
            "shift": pygame.K_LSHIFT,
            "lshift": pygame.K_LSHIFT,
            "rshift": pygame.K_RSHIFT,
            "alt": pygame.K_LALT,
            "lalt": pygame.K_LALT,
            "ralt": pygame.K_RALT,
            "up": pygame.K_UP,
            "down": pygame.K_DOWN,
            "left": pygame.K_LEFT,
            "right": pygame.K_RIGHT,
            "esc": pygame.K_ESCAPE,
            "escape": pygame.K_ESCAPE,
            "enter": pygame.K_RETURN,
            "return": pygame.K_RETURN,
            "space": pygame.K_SPACE,
            "tab": pygame.K_TAB,
            "backspace": pygame.K_BACKSPACE,
            "delete": pygame.K_DELETE,
            "home": pygame.K_HOME,
            "end": pygame.K_END,
            "pageup": pygame.K_PAGEUP,
            "pagedown": pygame.K_PAGEDOWN,
            "capslock": pygame.K_CAPSLOCK,
        }

        self.key_map.clear()

        if not self.btn_file_path or not os.path.exists(self.btn_file_path):
            print(f"[BtnHandeler] Missing config file: {self.btn_file_path}")
            return

        try:
            with open(self.btn_file_path, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()

                    if not line or line.startswith("#") or "=" not in line:
                        continue

                    name, key = line.split("=", 1)
                    name = name.strip().lower()
                    key = key.strip().lower()

                    if not name or not key:
                        continue

                    if key in special:
                        keycode = special[key]
                    else:
                        try:
                            keycode = pygame.key.key_code(key)
                        except Exception:
                            print(f"[BtnHandeler] Unknown key name: {key}")
                            continue

                    self.key_map[name] = keycode

        except Exception as e:
            print(f"[BtnHandeler] Failed to load config: {e}")

        self.current = {name: False for name in self.key_map}
        self.previous = {name: False for name in self.key_map}

    def _sync(self):
        pygame.event.pump()
        keys = pygame.key.get_pressed()

        self.previous = self.current.copy()

        for name, keycode in self.key_map.items():
            try:
                self.current[name] = bool(keys[keycode])
            except Exception:
                self.current[name] = False

    def _ensure_synced(self):
        tick = pygame.time.get_ticks()
        if tick != self._last_sync_tick:
            self._last_sync_tick = tick
            self._sync()

    def get_btn_pressed(self, btn):
        self._ensure_synced()
        return self.current.get(btn.lower(), False)

    def get_btn_down(self, btn):
        self._ensure_synced()
        b = btn.lower()
        return self.current.get(b, False) and not self.previous.get(b, False)

    def get_btn_up(self, btn):
        self._ensure_synced()
        b = btn.lower()
        return (not self.current.get(b, False)) and self.previous.get(b, False)

    def get_keycode(self, btn):
        return self.key_map.get(btn.lower())