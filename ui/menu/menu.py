import pygame
import json
import os
import math
import sys
import time
import threading
from datetime import datetime, date, timedelta

import requests
import pytz
from astral.sun import sun
from astral import LocationInfo

from assetsLoader import Loader


# TODO: FIX JOYSTICK BUG

OPTIONS_FILE = r"C:\TWOSFILES\options.json"

DEFAULT_OPTIONS = {
    "fullscreen": False,
    "master_volume": 0.5,
    "debug": 0.0,
}


# ─── Options file management ───────────────────────────────────────────────────

def ensure_options_file():
    options_dir = os.path.dirname(OPTIONS_FILE)
    if options_dir and not os.path.exists(options_dir):
        os.makedirs(options_dir, exist_ok=True)

    if not os.path.exists(OPTIONS_FILE):
        with open(OPTIONS_FILE, "w") as f:
            json.dump(DEFAULT_OPTIONS, f, indent=4)

    return OPTIONS_FILE


def save_options(options):
    path = ensure_options_file()
    with open(path, "w") as f:
        json.dump(options, f, indent=4)


def load_options():
    path = ensure_options_file()
    try:
        with open(path, "r") as f:
            options = json.load(f)
        for key, value in DEFAULT_OPTIONS.items():
            options.setdefault(key, value)
        return options
    except Exception:
        return dict(DEFAULT_OPTIONS)


# ─── Menu class ────────────────────────────────────────────────────────────────

class Menu:
    LOCATION_REFRESH_INTERVAL = 10 * 60   # 10 minutes
    SUNS_CALC_INTERVAL        = 60 * 60   # 1 hour

    def __init__(self, settings=None):
        pygame.mixer.init()
        pygame.joystick.init()

        # Main menu state
        self.options = ["Start Game", "Options", "Quit"]
        self.selected_index = 0
        self.running = True
        self.menu_rects = []

        # Settings state
        self.InSettings = False
        self.selected_setting = 0
        self.settings_options = [
            "Fullscreen", "Master Volume", "Controllers",
            "Go back", "Reset Game", "Debug",
        ]
        self.settings_rects = []

        # Slider state
        self.slider_width   = 300
        self.slider_height  = 10
        self.knob_radius    = 8
        self.slider_rects   = {}
        self.slider_knob_positions = {}
        self.active_slider  = None
        self.dragging_slider = False
        # Legacy single-slider references (kept for compat)
        self.slider_left   = None
        self.slider_top    = None
        self.slider_rect   = None
        self.knob_pos      = None

        # Joystick state
        self.joystick    = None
        self.joystick_id = None
        self.axis_deadzone = 0.4
        self.used = False

        # Location / sun cache
        self.cached_location    = None
        self.location_lock      = threading.Lock()
        self.last_location_fetch = None
        self.cached_sun         = None
        self.cached_sun_date    = None
        self.last_sun_calc      = None

        self.settings = settings if settings else load_options()
        self.clock = pygame.time.Clock()
        self.music_started = False

        self._load_assets()
        self._init_first_joystick()

        # Kick off a background location fetch immediately
        threading.Thread(target=self._background_location_fetch, daemon=True).start()

    # ─── Asset loading ──────────────────────────────────────────────────────────

    def _load_assets(self):
        loader = Loader("ui/menu/the_sun_is_a_deadly_laser")

        self.mini_sun = self._load_image(
            loader.load("miniboy -_-.png"),
            fallback=self._circle_surface(24, (255, 200, 0)),
        )
        self.big_sun = self._load_image(
            loader.load("BIGBOY.png"),
            fallback=self._circle_surface(96, (255, 220, 0)),
        )
        self.moon = self._load_image(
            loader.load("MOON.png"),
            fallback=self._circle_surface(96, (220, 220, 255)),
        )

        self.selector_icon = self._load_image(
            Loader("icon").load("lantern.png"),
            fallback=self._arrow_surface(),
        )

        try:
            font_path = Loader("ui/menu").load("PixelFont.ttf")
            self.font = pygame.font.Font(font_path, 30)
        except Exception:
            self.font = pygame.font.SysFont("Arial", 30)

        try:
            music_path = Loader("music").load("TitleV2.mp3")
            if music_path and os.path.exists(music_path):
                pygame.mixer.music.load(music_path)
        except Exception as e:
            print("Could not load music:", e)

        pygame.mixer.music.set_volume(self.settings.get("master_volume", 0.5))

        try:
            self.save_path = Loader("sprites/save").load("savedgame.TWOSSAVE")
        except Exception:
            self.save_path = os.path.join(os.getcwd(), "savedgame.TWOSSAVE")

    @staticmethod
    def _load_image(path, fallback):
        try:
            return pygame.image.load(path).convert_alpha()
        except Exception:
            return fallback

    @staticmethod
    def _circle_surface(size, color):
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(surf, color, (size // 2, size // 2), size // 2)
        return surf

    @staticmethod
    def _arrow_surface():
        surf = pygame.Surface((20, 20), pygame.SRCALPHA)
        pygame.draw.polygon(surf, (255, 255, 0), [(0, 0), (20, 10), (0, 20)])
        return surf

    # ─── Joystick ───────────────────────────────────────────────────────────────

    def _init_first_joystick(self):
        try:
            if pygame.joystick.get_count() > 0:
                joystick = pygame.joystick.Joystick(0)
                joystick.init()
                self.joystick    = joystick
                self.joystick_id = joystick.get_instance_id()
                print("Joystick connected:", joystick.get_name())
            else:
                self.joystick    = None
                self.joystick_id = None
        except Exception as e:
            print("Joystick init failed:", e)
            self.joystick    = None
            self.joystick_id = None

    # ─── Location / sun ─────────────────────────────────────────────────────────

    def _background_location_fetch(self):
        for _ in range(2):
            try:
                loc = self._fetch_location_once()
                if loc:
                    with self.location_lock:
                        self.cached_location     = loc
                        self.last_location_fetch = time.time()
                    self._recompute_sun()
                    return
            except Exception:
                pass
            time.sleep(1)

        with self.location_lock:
            self.last_location_fetch = time.time()

    def _fetch_location_once(self):
        try:
            data = requests.get("http://ip-api.com/json/", timeout=4).json()
            return (
                data.get("city", "Unknown"),
                data.get("country", "Unknown"),
                data.get("lat", 0.0),
                data.get("lon", 0.0),
                data.get("timezone"),
            )
        except Exception:
            return None

    def _periodic_location_and_sun_refresh(self):
        now = time.time()
        with self.location_lock:
            last_loc = self.last_location_fetch

        if last_loc is None or (now - last_loc) > self.LOCATION_REFRESH_INTERVAL:
            threading.Thread(target=self._background_location_fetch, daemon=True).start()

        if self.last_sun_calc is None or (now - self.last_sun_calc) > self.SUNS_CALC_INTERVAL:
            try:
                self._recompute_sun()
            except Exception as e:
                print("Sun recompute failed:", e)

    def _recompute_sun(self):
        with self.location_lock:
            loc = self.cached_location

        if not loc:
            self.cached_sun      = None
            self.cached_sun_date = None
            self.last_sun_calc   = time.time()
            return

        city, country, lat, lon, tz_name = loc

        tz = pytz.utc
        if tz_name:
            try:
                tz = pytz.timezone(tz_name)
            except Exception:
                pass

        location = LocationInfo(city or "Unknown", country or "Unknown", tz.zone, lat, lon)
        today = date.today()

        self.cached_sun      = sun(location.observer, date=today, tzinfo=tz)
        self.cached_sun_date = today
        self.last_sun_calc   = time.time()

    def is_sun_down(self):
        if self.cached_sun is None:
            with self.location_lock:
                if self.cached_location is None:
                    return False
            try:
                self._recompute_sun()
            except Exception:
                return False

        if self.cached_sun is None:
            return False

        tz      = self.cached_sun["sunrise"].tzinfo or pytz.utc
        now     = datetime.now(tz)
        sunrise = self.cached_sun.get("sunrise")
        sunset  = self.cached_sun.get("sunset")

        if sunrise is None or sunset is None:
            return False

        return (now < sunrise) or (now > sunset)

    # ─── Main draw loop ─────────────────────────────────────────────────────────

    def draw(self, screen):
        if not self.music_started:
            try:
                pygame.mixer.music.play(-1, fade_ms=1000)
            except Exception:
                pass
            self.music_started = True

        while self.running:
            self.clock.tick(60)

            screen.fill((0, 0, 127))

            mouse_pos = pygame.mouse.get_pos()

            # Highlight hovered menu/settings items
            for i, rect in enumerate(self.menu_rects):
                if rect.collidepoint(mouse_pos):
                    self.selected_index = i
            for i, rect in enumerate(self.settings_rects):
                if rect.collidepoint(mouse_pos):
                    self.selected_setting = i

            for event in pygame.event.get():
                self._handle_event(event, screen)

            # Joystick input
            if not self.InSettings:
                self.handle_mainmenu_input_joystick()
            else:
                self.handle_settings_input_joystick()

            # Draw
            if self.InSettings:
                self._periodic_location_and_sun_refresh()
                self.draw_settings(screen)
            else:
                self.draw_menu(screen)

            pygame.display.flip()

    def _handle_event(self, event, screen):
        if event.type == pygame.QUIT:
            pygame.mixer.music.fadeout(500)
            pygame.quit()
            sys.exit(0)

        if event.type == pygame.KEYDOWN:
            if self.InSettings:
                self.handle_settings_input(event, screen)
            else:
                self.handle_mainmenu_input(event)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self.InSettings:
                for i, rect in enumerate(self.menu_rects):
                    if rect.collidepoint(event.pos):
                        self.selected_index = i
                        self.activate_selected_option()
            else:
                for i, rect in enumerate(self.settings_rects):
                    if rect.collidepoint(event.pos):
                        self.selected_setting = i
                        self.change_setting(pygame.K_RETURN, screen)
                self._handle_settings_mouse_down(event.pos)

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.InSettings:
            self._handle_settings_mouse_up(event.pos)

        if event.type == pygame.MOUSEMOTION and self.InSettings:
            self._handle_settings_mouse_motion(event.pos)

        if event.type == pygame.JOYDEVICEADDED:
            print("Joystick added")
            self._init_first_joystick()

        if event.type == pygame.JOYDEVICEREMOVED:
            print("Joystick removed")
            self.joystick    = None
            self.joystick_id = None

    # ─── Main menu ──────────────────────────────────────────────────────────────

    def activate_selected_option(self):
        choice = self.options[self.selected_index]

        if choice == "Start Game":
            pygame.mixer.music.fadeout(1000)
            pygame.time.delay(500)
            self.running = False
            return "singleplayer"

        elif choice == "Options":
            self.InSettings = True

        elif choice == "Quit":
            sys.exit(0)

    def handle_mainmenu_input(self, event):
        if event.key == pygame.K_UP:
            self.selected_index = (self.selected_index - 1) % len(self.options)
        elif event.key == pygame.K_DOWN:
            self.selected_index = (self.selected_index + 1) % len(self.options)
        elif event.key == pygame.K_RETURN:
            self.activate_selected_option()

    def handle_mainmenu_input_joystick(self):
        if not self.joystick:
            return
        try:
            # Any face button confirms selection
            if any(self.joystick.get_button(b) for b in range(min(2, self.joystick.get_numbuttons()))):
                self.activate_selected_option()

            axis_x = self.joystick.get_axis(0)
            axis_y = self.joystick.get_axis(1)

            if not self.used:
                if axis_y < -0.5:
                    self.selected_index = (self.selected_index - 1) % len(self.options)
                    self.used = True
                elif axis_y > 0.5:
                    self.selected_index = (self.selected_index + 1) % len(self.options)
                    self.used = True

            if abs(axis_x) < 0.5 and abs(axis_y) < 0.5:
                self.used = False

        except Exception as e:
            print(e)
            self.joystick = None

    def draw_menu(self, screen):
        screen_width, screen_height = screen.get_size()
        y_start = screen_height // 2
        self.menu_rects = []

        # Non-selectable title in the top-left
        title_surface = self.font.render("The Weight of Shadows", True, (255, 255, 255))
        screen.blit(title_surface, (20, 20))

        for i, option in enumerate(self.options):
            color = (255, 255, 0) if i == self.selected_index else (255, 255, 255)
            text_surface = self.font.render(option, True, color)
            x = screen_width // 2 - text_surface.get_width() // 2
            y = y_start + i * (self.font.get_height() + 15)
            rect = text_surface.get_rect(topleft=(x, y))
            self.menu_rects.append(rect)
            screen.blit(text_surface, rect)

            if i == self.selected_index:
                icon_x = x - self.selector_icon.get_width() - 10
                icon_y = y + (text_surface.get_height() - self.selector_icon.get_height()) // 2
                screen.blit(self.selector_icon, (icon_x, icon_y))

    # ─── Settings ───────────────────────────────────────────────────────────────

    def handle_settings_input(self, event, screen):
        if event.key == pygame.K_UP:
            self.selected_setting = (self.selected_setting - 1) % len(self.settings_options)
        elif event.key == pygame.K_DOWN:
            self.selected_setting = (self.selected_setting + 1) % len(self.settings_options)
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            self.change_setting(event.key, screen)
        elif event.key == pygame.K_RETURN:
            self.handle_setting_select()
        elif event.key == pygame.K_ESCAPE:
            self.InSettings = False
            save_options(self.settings)

    def handle_settings_input_joystick(self):
        if not self.joystick:
            return
        try:
            if self.joystick.get_numbuttons() > 0 and self.joystick.get_button(0):
                self.InSettings = False
                save_options(self.settings)

            axis_x = self.joystick.get_axis(0)
            axis_y = self.joystick.get_axis(1)

            if not self.used:
                if axis_x < -0.5:
                    self.change_setting(pygame.K_LEFT, None)
                    self.used = True
                elif axis_x > 0.5:
                    self.change_setting(pygame.K_RIGHT, None)
                    self.used = True
                elif axis_y < -0.5:
                    self.selected_setting = (self.selected_setting - 1) % len(self.settings_options)
                    self.used = True
                elif axis_y > 0.5:
                    self.selected_setting = (self.selected_setting + 1) % len(self.settings_options)
                    self.used = True

            if abs(axis_x) < 0.5 and abs(axis_y) < 0.5:
                self.used = False

        except Exception:
            self.joystick = None

    def change_setting(self, key, screen):
        if self.selected_setting == 0:  # Fullscreen
            self.settings["fullscreen"] = not self.settings.get("fullscreen", False)
            if screen is not None:
                self.apply_fullscreen(screen)

        elif self.selected_setting == 1:  # Master Volume
            delta   = -0.05 if key == pygame.K_LEFT else 0.05
            new_vol = min(max(self.settings.get("master_volume", 0.5) + delta, 0.0), 1.0)
            self.settings["master_volume"] = new_vol
            pygame.mixer.music.set_volume(new_vol)
            save_options(self.settings)

    def handle_setting_select(self):
        if self.settings_options[self.selected_setting] == "Reset Game":
            try:
                if os.path.exists(self.save_path):
                    os.remove(self.save_path)
                    print("Save deleted!")
            except Exception as e:
                print("Could not delete save:", e)

        save_options(self.settings)
        self.InSettings = False

    def apply_fullscreen(self, screen):
        flags = pygame.SCALED | pygame.DOUBLEBUF
        if self.settings.get("fullscreen", False):
            flags |= pygame.FULLSCREEN
        try:
            current_size = screen.get_size()
        except Exception:
            current_size = (1066, 600)
        pygame.display.set_mode(current_size, flags)

    # ─── Settings draw ──────────────────────────────────────────────────────────

    def draw_settings(self, screen):
        screen.fill((0, 0, 127))
        self.settings_rects = []

        screen_width, screen_height = screen.get_size()
        left_margin = 50
        top_margin  = 300
        spacing     = 50

        for i, option in enumerate(self.settings_options):
            color = (255, 255, 0) if i == self.selected_setting else (255, 255, 255)

            label = option
            if option == "Fullscreen":
                label += f": {'ON' if self.settings.get('fullscreen', False) else 'OFF'}"
            elif option == "Master Volume":
                label += f": {int(self.settings.get('master_volume', 0.5) * 100)}%"
            elif option == "Debug":
                label += f": {self.settings.get('debug', 0.0):.2f}"

            text_x = left_margin
            text_y = top_margin + i * spacing
            rendered = self.font.render(label, True, color)

            self.settings_rects.append(
                pygame.Rect(text_x, text_y, screen_width - 2 * left_margin, self.font.get_height())
            )
            screen.blit(rendered, (text_x, text_y))

            if option in ("Master Volume", "Debug"):
                self._draw_inline_slider(screen, option.lower().replace(" ", "_"), rendered, text_x, text_y)

        self._draw_sun_or_moon(screen, screen_width)
        self._draw_day_label(screen)

    def _draw_inline_slider(self, screen, slider_name, label_surface, text_x, text_y):
        padding  = 20
        slider_x = text_x + label_surface.get_width() + padding
        slider_y = text_y + label_surface.get_height() // 2 - self.slider_height // 2

        self.slider_left = slider_x
        self.slider_top  = slider_y
        bar_rect = pygame.Rect(slider_x, slider_y, self.slider_width, self.slider_height)
        self.slider_rects[slider_name] = bar_rect

        value  = self.settings.get(slider_name, 0.0)
        fill_w = int(self.slider_width * value)

        # Track
        pygame.draw.rect(screen, (80, 80, 80), bar_rect, border_radius=6)
        # Fill
        if fill_w > 0:
            pygame.draw.rect(screen, (255, 200, 50),
                             (slider_x, slider_y, fill_w, self.slider_height), border_radius=6)

        # Knob
        knob_x = slider_x + fill_w
        knob_y = slider_y + self.slider_height // 2
        self.slider_knob_positions[slider_name] = (knob_x, knob_y)
        pygame.draw.circle(screen, (230, 230, 230), (knob_x, knob_y), self.knob_radius)
        pygame.draw.circle(screen, (120, 120, 120), (knob_x, knob_y), self.knob_radius, 2)

    def _draw_sun_or_moon(self, screen, screen_width):
        center_x = screen_width - 150
        center_y = 140
        orbit_r  = 40

        if not self.is_sun_down():
            t = pygame.time.get_ticks() / 1000.0
            base_angle = (t * 40.0) % 360.0  # 40 deg/sec spin

            for i in range(10):
                angle = math.radians(base_angle + i * 36)
                x = int(center_x + math.cos(angle) * orbit_r - self.mini_sun.get_width()  // 2)
                y = int(center_y - math.sin(angle) * orbit_r - self.mini_sun.get_height() // 2)
                screen.blit(self.mini_sun, (x, y))

            screen.blit(self.big_sun, (
                center_x - self.big_sun.get_width()  // 2,
                center_y - self.big_sun.get_height() // 2,
            ))
        else:
            screen.blit(self.moon, (
                center_x - self.moon.get_width()  // 2,
                center_y - self.moon.get_height() // 2,
            ))

    def _draw_day_label(self, screen):
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_short = day_names[datetime.now().weekday()][:3]
        surface   = self.font.render(day_short, True, (255, 255, 255))
        x = screen.get_width() // 2 - surface.get_width() // 2
        y = 150 - self.big_sun.get_height() // 2
        screen.blit(surface, (x, y))

    # ─── Slider mouse handling ──────────────────────────────────────────────────

    def _handle_settings_mouse_down(self, pos):
        mx, my = pos

        for slider_name, rect in self.slider_rects.items():
            kx, ky = self.slider_knob_positions.get(slider_name, (0, 0))
            on_knob = (mx - kx) ** 2 + (my - ky) ** 2 <= (self.knob_radius + 4) ** 2
            if on_knob or rect.collidepoint(pos):
                self.active_slider   = slider_name
                self.dragging_slider = True
                self._set_slider_value_by_mouse(mx, slider_name)
                return

        # Click on text rows
        left_margin = 50
        top_margin  = 120
        spacing     = 50
        for i, option in enumerate(self.settings_options):
            rendered = self.font.render(option, True, (255, 255, 255))
            rect = rendered.get_rect(topleft=(left_margin, top_margin + i * spacing))

            if option == "Master Volume":
                extra = self.font.render(f": {int(self.settings.get('master_volume', 0.5) * 100)}%", True, (255, 255, 255))
                rect.width += extra.get_width() + 20

            if rect.collidepoint(pos):
                self.selected_setting = i
                if option == "Fullscreen":
                    self.settings["fullscreen"] = not self.settings.get("fullscreen", False)
                    save_options(self.settings)
                    try:
                        self.apply_fullscreen(pygame.display.get_surface())
                    except Exception:
                        pass
                elif option == "Reset Game":
                    try:
                        if os.path.exists(self.save_path):
                            os.remove(self.save_path)
                            print("Save deleted!")
                    except Exception:
                        pass
                return

    def _handle_settings_mouse_up(self, pos):
        if self.dragging_slider:
            self.dragging_slider = False
            save_options(self.settings)

    def _handle_settings_mouse_motion(self, pos):
        if self.dragging_slider and self.active_slider:
            self._set_slider_value_by_mouse(pos[0], self.active_slider)

    def _set_slider_value_by_mouse(self, mx, slider_name):
        slider_rect = self.slider_rects.get(slider_name)
        if not slider_rect:
            return

        rel_x     = max(0, min(mx - slider_rect.left, slider_rect.width))
        new_value = round(rel_x / float(slider_rect.width), 3)

        if abs(new_value - self.settings.get(slider_name, 0.0)) < 0.0001:
            return

        self.settings[slider_name] = new_value
        if slider_name == "master_volume":
            pygame.mixer.music.set_volume(new_value)

        fill_w = int(self.slider_width * new_value)
        self.slider_knob_positions[slider_name] = (
            slider_rect.left + fill_w,
            slider_rect.top + self.slider_height // 2,
        )