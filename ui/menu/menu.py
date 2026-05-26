import pygame

import json

import os

import math

from assetsLoader import Loader

import requests

from datetime import datetime, date, timedelta

from astral.sun import sun

from astral import LocationInfo

import pytz

import threading

import time

import sys



#TODO: FIX JOYSTICK BUG



OPTIONS_FILE = r"C:\TWOSFILES\options.json"



# -------------------------

#  OPTIONS FILE MANAGEMENT

# -------------------------



def ensure_options_file():

    options_path = OPTIONS_FILE

    options_dir = os.path.dirname(options_path)

    if options_dir and not os.path.exists(options_dir):

        os.makedirs(options_dir, exist_ok=True)

    default_options = {"fullscreen": False, "master_volume": 0.5, "debug": 0.0}

    if not os.path.exists(options_path):

        with open(options_path, "w") as f:

            json.dump(default_options, f, indent=4)

    return options_path





def save_options(options):

    path = ensure_options_file()

    with open(path, "w") as f:

        json.dump(options, f, indent=4)





def load_options():

    path = ensure_options_file()

    try:

        with open(path, "r") as f:

            options = json.load(f)
            options.setdefault("fullscreen", False)
            options.setdefault("master_volume", 0.5)
            options.setdefault("debug", 0.0)
            return options

    except Exception:

        return {"fullscreen": False, "master_volume": 0.5, "debug": 0.0}



class Menu:

    # How often we attempt to refresh the location (seconds)

    LOCATION_REFRESH_INTERVAL = 10 * 60  # 10 minutes

    # How often we recalc sunrise/sunset (seconds) - once per day is enough but small buffer allowed

    SUNS_CALC_INTERVAL = 60 * 60  # 1 hour (we'll also only recompute for a new date)



    def __init__(self, settings=None):

        pygame.mixer.init()

        pygame.joystick.init()



        self.options = ["Start Game", "Options", "Quit"]

        self.selected_index = 0

        self.running = True



        self.InSettings = False

        self.selected_setting = 0

        self.settings_options = ["Fullscreen", "Master Volume", "Controllers", "Go back", "Reset Game", "Debug"]



        self.menu_rects = []



        # Load assets once

        self.loader = Loader("ui/menu/the_sun_is_a_deadly_laser")

        self.big_sun_path = self.loader.load("BIGBOY.png")

        self.miniboy_path = self.loader.load("miniboy -_-.png")

        self.moon_path = self.loader.load("MOON.png")



        # load images with safe fallbacks

        try:

            self.mini_sun = pygame.image.load(self.miniboy_path).convert_alpha()

        except Exception:

            self.mini_sun = pygame.Surface((24, 24), pygame.SRCALPHA)

            pygame.draw.circle(self.mini_sun, (255, 200, 0), (12, 12), 12)



        try:

            self.big_sun = pygame.image.load(self.big_sun_path).convert_alpha()

        except Exception:

            self.big_sun = pygame.Surface((96, 96), pygame.SRCALPHA)

            pygame.draw.circle(self.big_sun, (255, 220, 0), (48, 48), 48)



        try:

            self.moon = pygame.image.load(self.moon_path).convert_alpha()

        except Exception:

            self.moon = pygame.Surface((96, 96), pygame.SRCALPHA)

            pygame.draw.circle(self.moon, (220, 220, 255), (48, 48), 48)



        self.clock = pygame.time.Clock()

        self.music_started = False



        self.settings = settings if settings else load_options()



        # Load selector icon

        try:

            icon_loader = Loader("icon")

            icon_path = icon_loader.load("lantern.png")

            self.selector_icon = pygame.image.load(icon_path).convert_alpha()

        except Exception:

            self.selector_icon = pygame.Surface((20, 20), pygame.SRCALPHA)

            pygame.draw.polygon(self.selector_icon, (255, 255, 0),

                                [(0, 0), (20, 10), (0, 20)])



        # Load font

        try:

            font_loader = Loader("ui/menu")

            font_path = font_loader.load("PixelFont.ttf")

            self.font = pygame.font.Font(font_path, 30)

        except Exception:

            self.font = pygame.font.SysFont("Arial", 30)



        # Load music

        try:

            music_loader = Loader("music")

            music_path = music_loader.load("TitleV2.mp3")

            if music_path and os.path.exists(music_path):

                pygame.mixer.music.load(music_path)

        except Exception as e:

            print("Kon muziek niet laden:", e)



        pygame.mixer.music.set_volume(self.settings.get("master_volume", 0.5))



        # Save file

        try:

            self.save_path = Loader("sprites/save").load("savedgame.TWOSSAVE")

        except Exception:

            self.save_path = os.path.join(os.getcwd(), "savedgame.TWOSSAVE")



        # Joystick

        self.joystick = None

        self.joystick_id = None

        self.axis_deadzone = 0.4

        self.used = False



        pygame.joystick.init()

        self._init_first_joystick()



        # ------------- location & sun caching -------------

        # cached_location: (city, country, lat, lon, tz_name_or_None)

        self.cached_location = None

        self.location_lock = threading.Lock()

        self.last_location_fetch = None



        # cached sunrise/sunset dict and when it was computed (a date)

        self.cached_sun = None

        self.cached_sun_date = None

        self.last_sun_calc = None



        # Slider state (inline slider for Master Volume)

        self.slider_left = None

        self.slider_top = None

        self.slider_width = 300  # width of the slider bar

        self.slider_height = 10

        self.knob_radius = 8

        self.slider_rect = None
        self.knob_pos = None
        self.slider_rects = {}
        self.slider_knob_positions = {}
        self.active_slider = None

        self.dragging_slider = False

        self.settings_rects = []



        # Start a short background thread to fetch location immediately (non-blocking)

        t = threading.Thread(target=self._background_location_fetch, daemon=True)

        t.start()



    # -------------------------

    #     JOYSTICK SETUP

    # -------------------------



    def _init_first_joystick(self):

        """Initialize first available joystick safely."""

        try:

            count = pygame.joystick.get_count()



            if count > 0:

                joystick = pygame.joystick.Joystick(0)

                joystick.init()



                self.joystick = joystick

                self.joystick_id = joystick.get_instance_id()



                print("Joystick connected:", joystick.get_name())



            else:

                self.joystick = None

                self.joystick_id = None



        except Exception as e:

            print("Joystick init failed:", e)

            self.joystick = None

            self.joystick_id = None

    # -------------------------

    # BACKGROUND LOCATION FETCH

    # -------------------------



    def _background_location_fetch(self):

        """

        Fetches location in the background, with a timeout and retry policy.

        This will update self.cached_location and timestamps.

        """

        # attempt a couple of times immediately in case of a transient failure

        attempts = 2

        for attempt in range(attempts):

            try:

                loc = self._fetch_location_once()

                if loc:

                    with self.location_lock:

                        self.cached_location = loc

                        self.last_location_fetch = time.time()

                    # compute sun immediately after successful location fetch

                    self._recompute_sun()

                    return

            except Exception:

                # swallow exceptions here - background thread shouldn't crash

                pass

            time.sleep(1)

        # if we get here, initial fetch failed; record a timestamp so we can retry later from main thread logic

        with self.location_lock:

            self.last_location_fetch = time.time()



    def _fetch_location_once(self):

        """

        Attempt to fetch geolocation. Returns (city, country, lat, lon, tz_name_or_None) or None.

        Uses a short timeout so it never hangs.

        """

        try:

            resp = requests.get("http://ip-api.com/json/", timeout=4)

            data = resp.json()

            city = data.get("city", "Unknown")

            country = data.get("country", "Unknown")

            lat = data.get("lat", 0.0)

            lon = data.get("lon", 0.0)

            # ip-api returns timezone as 'timezone' sometimes

            tz_name = data.get("timezone")

            return (city, country, lat, lon, tz_name)

        except Exception:

            return None



    # -------------------------

    #     MAIN DRAW LOOP

    # -------------------------



    def draw(self, screen):



        if not self.music_started:

            try:

                pygame.mixer.music.play(-1, fade_ms=1000)

            except Exception:

                pass

            self.music_started = True



        while self.running:

            dt = self.clock.tick(60)



            screen.fill((0, 0, 127))







            mouse_pos = pygame.mouse.get_pos()

            for i, rect in enumerate(self.menu_rects):

                if rect.collidepoint(mouse_pos):

                    self.selected_index = i



            for i, rect in enumerate(self.settings_rects):

                if rect.collidepoint(mouse_pos):

                    self.selected_setting = i





            for event in pygame.event.get():

                if event.type == pygame.QUIT:

                    pygame.mixer.music.fadeout(500)

                    pygame.quit()

                    sys.exit(0)



                # Main menu mouse click

                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and not self.InSettings:

                    for i, rect in enumerate(self.menu_rects):

                        if rect.collidepoint(event.pos):

                            self.selected_index = i

                            self.activate_selected_option()



                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.InSettings:

                    for i, rect in enumerate(self.settings_rects):

                        if rect.collidepoint(event.pos):

                            self.selected_setting = i

                            self.change_setting(pygame.K_RETURN, screen)





                # Settings mouse events (click, drag, release)

                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.InSettings:

                    self._handle_settings_mouse_down(event.pos)

                if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.InSettings:

                    self._handle_settings_mouse_up(event.pos)

                if event.type == pygame.MOUSEMOTION and self.InSettings:

                    self._handle_settings_mouse_motion(event.pos)



                if event.type == pygame.KEYDOWN:

                    if self.InSettings:

                        self.handle_settings_input(event, screen)



                    else:

                        self.handle_mainmenu_input(event)



                if event.type == pygame.JOYDEVICEADDED:

                    print("Joystick added")

                    self._init_first_joystick()



                if event.type == pygame.JOYDEVICEREMOVED:

                    print("Joystick removed")

                    self.joystick = None

                    self.joystick_id = None



            if not self.InSettings:

                self.handle_mainmenu_input_joystick()

            else:

                self.handle_settings_input_joystick()



            if self.InSettings:

                # Occasionally refresh location/sun if needed (non-blocking)

                self._periodic_location_and_sun_refresh()

                self.draw_settings(screen)

            else:

                self.draw_menu(screen)



            pygame.display.flip()



    # -------------------------

    #      MENU INPUT

    # -------------------------



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

            sys.exit(0) #Fuck it



    def handle_mainmenu_input(self, event):

        if event.key == pygame.K_UP:

            self.selected_index = (self.selected_index - 1) % len(self.options)

        elif event.key == pygame.K_DOWN:

            self.selected_index = (self.selected_index + 1) % len(self.options)

        elif event.key == pygame.K_RETURN:

            self.activate_selected_option()



    # -------------------------

    #     SETTINGS INPUT

    # -------------------------



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



    # -------------------------

    #   JOYSTICK MAIN MENU

    # -------------------------



    def handle_mainmenu_input_joystick(self):

        if not self.joystick:

            return



        try:

            if self.joystick.get_numbuttons() > 0 and (self.joystick.get_button(0) or self.joystick.get_button(1)):

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

            self.joystick = None

            print(e)



    # -------------------------

    #   JOYSTICK SETTINGS

    # -------------------------



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



    # -------------------------

    #        DRAW MENU

    # -------------------------



    def draw_menu(self, screen):

        screen_width, screen_height = screen.get_size()

        y_start = screen_height // 2



        self.menu_rects = []



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



    # -------------------------

    #     SETTINGS UTILITIES

    # -------------------------



    def _periodic_location_and_sun_refresh(self):

        """

        Called from the main loop occasionally to ensure we refresh location/sun info

        with sensible intervals. This function is non-blocking.

        """

        now = time.time()

        with self.location_lock:

            last_loc = self.last_location_fetch



        # If we never fetched or it's been too long, attempt a short background fetch

        if last_loc is None or (now - last_loc) > self.LOCATION_REFRESH_INTERVAL:

            # Spawn a short background fetcher to avoid main thread blocking

            t = threading.Thread(target=self._background_location_fetch, daemon=True)

            t.start()



        # Recompute sun if it is stale (we prefer recompute in main thread but it is fast compared to network)

        if self.last_sun_calc is None or (now - (self.last_sun_calc or 0)) > self.SUNS_CALC_INTERVAL:

            # computing sun uses cached location and is fairly fast; do it in main thread but safe-guarded

            try:

                self._recompute_sun()

            except Exception as e:

                print("Sun recompute failed:", e)



    def _recompute_sun(self):

        """

        Compute sunrise/sunset for today based on cached_location.

        This will not block on network and will only run when cached_location exists.

        """

        with self.location_lock:

            loc = self.cached_location



        if not loc:

            # no location available; clear cached_sun so UI uses fallback

            self.cached_sun = None

            self.cached_sun_date = None

            self.last_sun_calc = time.time()

            return



        city, country, lat, lon, tz_name = loc



        # Choose timezone: prefer tz_name from geolocation if present, else UTC

        tz = pytz.utc

        if tz_name:

            try:

                tz = pytz.timezone(tz_name)

            except Exception:

                tz = pytz.utc



        # Astral expects a LocationInfo (name, region, timezone, lat, lon)

        location = LocationInfo(city or "Unknown", country or "Unknown", tz.zone, lat, lon)



        # Use today's date in that timezone to compute sunrise/sunset

        today = date.today()

        s = sun(location.observer, date=today, tzinfo=tz)



        self.cached_sun = s  # dict with 'sunrise','sunset',etc.

        self.cached_sun_date = today

        self.last_sun_calc = time.time()



    def is_sun_down(self):

        """

        Non-blocking check. Uses cached data. If no cached data available, returns False (assume day).

        """

        # If we don't have cached sun data, attempt a quick non-blocking recompute (will only run if location exists)

        if self.cached_sun is None:

            # if no location, don't block â€” return False (show sun)

            with self.location_lock:

                if self.cached_location is None:

                    return False

            # try to compute quickly (safe)

            try:

                self._recompute_sun()

            except Exception:

                return False



        if self.cached_sun is None:

            return False



        # Use timezone-aware now consistent with cached_sun timezone

        tz = self.cached_sun['sunrise'].tzinfo or pytz.utc

        now = datetime.now(tz)



        # Consider sun down if before sunrise or after sunset

        sunrise = self.cached_sun.get('sunrise')

        sunset = self.cached_sun.get('sunset')

        if (sunrise is None) or (sunset is None):

            return False



        return (now < sunrise) or (now > sunset)



    # -------------------------

    #     DRAW SETTINGS UI

    # -------------------------



    def draw_settings(self, screen):

        screen.fill((0, 0, 127))

        self.settings_rects = []

        screen_width, screen_height = screen.get_size()

        left_margin = 50

        top_margin = 300

        spacing = 50



        # Draw settings options on the left

        for i, option in enumerate(self.settings_options):

            self.settings_rects.append(pygame.Rect(left_margin, top_margin + i * spacing,

                                                  screen_width - 2 * left_margin, self.font.get_height()))

            color = (255, 255, 0) if i == self.selected_setting else (255, 255, 255)

            text = option



            # For adjustable settings, show current value

            if option == "Fullscreen":

                text += f": {'ON' if self.settings.get('fullscreen', False) else 'OFF'}"

            elif option == "Master Volume":

                vol = int(self.settings.get('master_volume', 0.5) * 100)

                text += f": {vol}%"
            elif option == "Debug":

                debug_val = self.settings.get('debug', 0.0)
                text += f": {debug_val:.2f}"



            rendered = self.font.render(text, True, color)

            text_x = left_margin

            text_y = top_margin + i * spacing

            screen.blit(rendered, (text_x, text_y))



            # If this is the master volume row, draw inline slider to the right of the text

            if option == "Master Volume":

                # compute slider geometry (placed inline to the right of the text)

                padding = 20

                text_width = rendered.get_width()

                slider_x = text_x + text_width + padding

                slider_y = text_y + rendered.get_height() // 2 - self.slider_height // 2

                self.slider_left = slider_x

                self.slider_top = slider_y

                self.slider_rects["master_volume"] = pygame.Rect(slider_x, slider_y, self.slider_width, self.slider_height)



                # draw bar

                pygame.draw.rect(screen, (80, 80, 80), self.slider_rects["master_volume"], border_radius=6)

                # draw filled portion

                vol = self.settings.get("master_volume", 0.5)

                fill_w = int(self.slider_width * vol)

                if fill_w > 0:

                    pygame.draw.rect(screen, (255, 200, 50), (slider_x, slider_y, fill_w, self.slider_height), border_radius=6)



                # compute knob position

                knob_x = slider_x + fill_w

                knob_y = slider_y + self.slider_height // 2

                self.slider_knob_positions["master_volume"] = (int(knob_x), int(knob_y))



                # draw knob (circle)

                pygame.draw.circle(screen, (230, 230, 230), self.slider_knob_positions["master_volume"], self.knob_radius)

                # knob outline

                pygame.draw.circle(screen, (120, 120, 120), self.slider_knob_positions["master_volume"], self.knob_radius, 2)


            if option == "Debug":

                # compute slider geometry (placed inline to the right of the text)

                padding = 20

                text_width = rendered.get_width()

                slider_x = text_x + text_width + padding

                slider_y = text_y + rendered.get_height() // 2 - self.slider_height // 2

                self.slider_left = slider_x

                self.slider_top = slider_y

                self.slider_rects["debug"] = pygame.Rect(slider_x, slider_y, self.slider_width, self.slider_height)



                # draw bar

                pygame.draw.rect(screen, (80, 80, 80), self.slider_rects["debug"], border_radius=6)

                # draw filled portion

                debug_val = self.settings.get("debug", 0.0)

                fill_w = int(self.slider_width * debug_val)

                if fill_w > 0:

                    pygame.draw.rect(screen, (255, 200, 50), (slider_x, slider_y, fill_w, self.slider_height), border_radius=6)



                # compute knob position

                knob_x = slider_x + fill_w

                knob_y = slider_y + self.slider_height // 2

                self.slider_knob_positions["debug"] = (int(knob_x), int(knob_y))



                # draw knob (circle)

                pygame.draw.circle(screen, (230, 230, 230), self.slider_knob_positions["debug"], self.knob_radius)

                # knob outline

                pygame.draw.circle(screen, (120, 120, 120), self.slider_knob_positions["debug"], self.knob_radius, 2)



        # Determine whether it's day or night using cached data (non-blocking)

        sun_down = self.is_sun_down()



        # Draw suns on the right (or moon if night)

        center_x = screen_width - 150

        center_y = 140

        radius = 40



        if not sun_down:

            # draw small suns around big sun; we can blit them with pre-loaded images

            for i in range(10):

                angle = i * 36

                dx = math.cos(math.radians(angle)) * radius

                dy = -math.sin(math.radians(angle)) * radius

                

                    # animated orbiting mini-suns

            t = pygame.time.get_ticks() / 1000.0  # seconds

            spin_speed_deg_per_sec = 40.0  # adjust speed

            n = 10

            base_angle = (t * spin_speed_deg_per_sec) % 360.0

            for i in range(n):

                angle_deg = base_angle + i * (360.0 / n)

                angle_rad = math.radians(angle_deg)

                dx = math.cos(angle_rad) * radius

                dy = -math.sin(angle_rad) * radius

                x = int(center_x + dx - self.mini_sun.get_width() // 2)

                y = int(center_y + dy - self.mini_sun.get_height() // 2)

                screen.blit(self.mini_sun, (x, y))



            screen.blit(

                self.big_sun,

                (center_x - self.big_sun.get_width() // 2,

                 center_y - self.big_sun.get_height() // 2)

            )

        else:



            screen.blit(

                self.moon,

                (center_x - self.big_sun.get_width() // 2,

                 center_y - self.big_sun.get_height() // 2)

            )



        # Draw day of week above suns (3-letter)

        day_text = datetime.now().weekday()

        day_text = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][day_text]

        day_text_short = day_text[:3]



        day_surface = self.font.render(day_text_short, True, (255, 255, 255))

        screen.blit(day_surface, (screen.get_width() // 2 - day_surface.get_width() // 2, 150 - self.big_sun.get_height() // 2))



    # -------------------------

    #   CHANGE SETTINGS

    # -------------------------



    def change_setting(self, key, screen):

        if self.selected_setting == 0:

            self.settings["fullscreen"] = not self.settings.get("fullscreen", False)

            if screen is not None:

                self.apply_fullscreen(screen)



        elif self.selected_setting == 1:

            delta = -0.05 if key == pygame.K_LEFT else 0.05

            new_vol = min(max(self.settings.get("master_volume", 0.5) + delta, 0), 1)

            self.settings["master_volume"] = new_vol

            pygame.mixer.music.set_volume(new_vol)

            save_options(self.settings)



    # -------------------------

    #   SELECT SETTING

    # -------------------------



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



    # -------------------------

    #     APPLY FULLSCREEN

    # -------------------------



    def apply_fullscreen(self, screen):

        flags = pygame.SCALED | pygame.DOUBLEBUF

        if self.settings.get("fullscreen", False):

            flags |= pygame.FULLSCREEN



        # Use current video mode size to preserve resolution

        try:

            current_size = screen.get_size()

        except Exception:

            current_size = (1066, 600)



        pygame.display.set_mode(current_size, flags)



    # -------------------------

    #   MOUSE HANDLING FOR SETTINGS + SLIDER

    # -------------------------



    def _handle_settings_mouse_down(self, pos):

        """Handle mouse down in settings screen (start dragging or toggle items)."""

        mx, my = pos



        # First, check if any slider exists and mouse is on a knob or bar

        for slider_name, rect in self.slider_rects.items():

            knob_x, knob_y = self.slider_knob_positions.get(slider_name, (0, 0))

            # distance to knob

            if (mx - knob_x) ** 2 + (my - knob_y) ** 2 <= (self.knob_radius + 4) ** 2:

                self.active_slider = slider_name

                self.dragging_slider = True

                return

            # click on bar

            if rect.collidepoint(pos):

                self.active_slider = slider_name

                self._set_slider_value_by_mouse(mx, slider_name)

                self.dragging_slider = True

                return



        # If not clicking slider, check text rows (toggle fullscreen/reset, select setting)

        left_margin = 50

        top_margin = 120

        spacing = 50

        for i, option in enumerate(self.settings_options):

            rendered = self.font.render(option, True, (255, 255, 255))

            text_x = left_margin

            text_y = top_margin + i * spacing

            rect = rendered.get_rect(topleft=(text_x, text_y))

            # Extend rect to include volume text for master volume row

            if option == "Master Volume":

                vol_text = f": {int(self.settings.get('master_volume', 0.5)*100)}%"

                vol_render = self.font.render(vol_text, True, (255,255,255))

                rect.width += vol_render.get_width() + 20



            if rect.collidepoint(pos):

                self.selected_setting = i

                # Immediate actions for clicks on rows:

                if option == "Fullscreen":

                    self.settings["fullscreen"] = not self.settings.get("fullscreen", False)

                    save_options(self.settings)

                    # apply immediately

                    try:

                        self.apply_fullscreen(pygame.display.get_surface())

                    except Exception:

                        pass

                    return

                elif option == "Reset Game":

                    try:

                        if os.path.exists(self.save_path):

                            os.remove(self.save_path)

                            print("Save deleted!")

                    except Exception:

                        pass

                    return



    def _handle_settings_mouse_up(self, pos):

        """Stop dragging and save settings if changed."""

        if self.dragging_slider:

            self.dragging_slider = False

            save_options(self.settings)



    def _handle_settings_mouse_motion(self, pos):

        """If dragging the slider, update the selected slider in real-time."""

        if self.dragging_slider and self.active_slider:

            mx, my = pos

            self._set_slider_value_by_mouse(mx, self.active_slider)



    def _set_slider_value_by_mouse(self, mx, slider_name):

        """Set a slider value based on absolute mouse x position over the slider bar."""

        slider_rect = self.slider_rects.get(slider_name)

        if not slider_rect:

            return

        rel_x = mx - slider_rect.left

        rel_x = max(0, min(rel_x, slider_rect.width))

        new_value = rel_x / float(slider_rect.width)

        # clamp and round a bit for neatness

        new_value = round(max(0.0, min(new_value, 1.0)), 3)

        current_value = self.settings.get(slider_name, 0.0)

        if abs(new_value - current_value) < 0.0001:

            return

        self.settings[slider_name] = new_value

        if slider_name == "master_volume":

            pygame.mixer.music.set_volume(new_value)

        # update knob position for immediate visuals

        fill_w = int(self.slider_width * new_value)

        knob_x = slider_rect.left + fill_w

        knob_y = slider_rect.top + self.slider_height // 2

        self.slider_knob_positions[slider_name] = (int(knob_x), int(knob_y))



    # -------------------------

    #   SELECT SETTINGS & HELPERS

    # -------------------------



    def _periodic_location_and_sun_refresh(self):

        """

        Called from the main loop occasionally to ensure we refresh location/sun info

        with sensible intervals. This function is non-blocking.

        """

        now = time.time()

        with self.location_lock:

            last_loc = self.last_location_fetch



        # If we never fetched or it's been too long, attempt a short background fetch

        if last_loc is None or (now - last_loc) > self.LOCATION_REFRESH_INTERVAL:

            # Spawn a short background fetcher to avoid main thread blocking

            t = threading.Thread(target=self._background_location_fetch, daemon=True)

            t.start()



        # Recompute sun if it is stale (we prefer recompute in main thread but it is fast compared to network)

        if self.last_sun_calc is None or (now - (self.last_sun_calc or 0)) > self.SUNS_CALC_INTERVAL:

            # computing sun uses cached location and is fairly fast; do it in main thread but safe-guarded

            try:

                self._recompute_sun()

            except Exception as e:

                print("Sun recompute failed:", e)



    def _recompute_sun(self):

        """

        Compute sunrise/sunset for today based on cached_location.

        This will not block on network and will only run when cached_location exists.

        """

        with self.location_lock:

            loc = self.cached_location



        if not loc:

            # no location available; clear cached_sun so UI uses fallback

            self.cached_sun = None

            self.cached_sun_date = None

            self.last_sun_calc = time.time()

            return



        city, country, lat, lon, tz_name = loc



        # Choose timezone: prefer tz_name from geolocation if present, else UTC

        tz = pytz.utc

        if tz_name:

            try:

                tz = pytz.timezone(tz_name)

            except Exception:

                tz = pytz.utc



        # Astral expects a LocationInfo (name, region, timezone, lat, lon)

        location = LocationInfo(city or "Unknown", country or "Unknown", tz.zone, lat, lon)



        # Use today's date in that timezone to compute sunrise/sunset

        today = date.today()

        s = sun(location.observer, date=today, tzinfo=tz)



        self.cached_sun = s  # dict with 'sunrise','sunset',etc.

        self.cached_sun_date = today

        self.last_sun_calc = time.time()



    def is_sun_down(self):

        """

        Non-blocking check. Uses cached data. If no cached data available, returns False (assume day).

        """

        # If we don't have cached sun data, attempt a quick non-blocking recompute (will only run if location exists)

        if self.cached_sun is None:

            # if no location, don't block â€” return False (show sun)

            with self.location_lock:

                if self.cached_location is None:

                    return False

            # try to compute quickly (safe)

            try:

                self._recompute_sun()

            except Exception:

                return False



        if self.cached_sun is None:

            return False



        # Use timezone-aware now consistent with cached_sun timezone

        tz = self.cached_sun['sunrise'].tzinfo or pytz.utc

        now = datetime.now(tz)



        # Consider sun down if before sunrise or after sunset

        sunrise = self.cached_sun.get('sunrise')

        sunset = self.cached_sun.get('sunset')

        if (sunrise is None) or (sunset is None):

            return False



        return (now < sunrise) or (now > sunset)



    # -------------------------

    #   OTHER UI & HELPERS

    # -------------------------



    def change_setting(self, key, screen):

        if self.selected_setting == 0:

            self.settings["fullscreen"] = not self.settings.get("fullscreen", False)

            if screen is not None:

                self.apply_fullscreen(screen)



        elif self.selected_setting == 1:

            delta = -0.05 if key == pygame.K_LEFT else 0.05

            new_vol = min(max(self.settings.get("master_volume", 0.5) + delta, 0), 1)

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





