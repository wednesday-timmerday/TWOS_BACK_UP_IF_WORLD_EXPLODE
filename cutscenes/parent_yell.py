import pygame
import sys
import random
from assetsLoader import Loader
import pytweening
import math
import threading

# Module-level cache so images/sounds load once in background and persist across replays
_ASSET_CACHE = {
    "goreimgs": [],
    "hand": None,
    "clicksfx": None,
    "loaded": False,
    "loading": False,
}
_CACHE_LOCK = threading.Lock()


class cutscene:

    def __init__(self, player, world, loader):
        self.dialogue_id = "parent_yell"
        self.player = player
        self.world = world
        self.loader = loader
        self.dt = 0
        self.FREEDOMTIMER = 0

        # Shaking offsets (evaluated every frame, no interval delay)
        # On a 320x180 canvas (upscaled 4x to 1280x720), 1 unit = 1 pixel (4 screen pixels).
        # [0, 1] gives the tiniest possible shake (1 pixel swing, half of [-1, 1]).
        # [0] for Y keeps the player grounded without vertical bouncing.
        self.shake_offsets_x = [0, 1]
        self.shake_offsets_y = [0, 1]

        self.show_black_screen = False

        self.goto_world_stage = 1
        self.goto_world_wait = 0.0
        self.total_frames_elapsed = 0
        self.slide_t = 0.0
        self.slide_start_x = 0
        self.slide_distance = 50
        self.slide_duration = 0.8
        self.show_black = True

        self.radius_offset = 2500

        self.gore_frame_time = 1 / 12
        self.gore_timer = 0.0
        self.gore_index = 0
        self.gore_last_index = -1

        self.itswarm = True

        self.fade_alpha = 0
        self.fade_t = 0.0
        self.fade_duration = 1.0

        self.last_gore_image_time = 3

        # Start background asset loading if not already in cache
        with _CACHE_LOCK:
            needs_load = not _ASSET_CACHE["loaded"] and not _ASSET_CACHE["loading"]
            if needs_load:
                _ASSET_CACHE["loading"] = True

        if needs_load:
            threading.Thread(target=self._load_assets_async, daemon=True).start()

    @property
    def goreimgs(self):
        return _ASSET_CACHE["goreimgs"]

    @property
    def hand(self):
        return _ASSET_CACHE["hand"]

    @property
    def clicksfx(self):
        return _ASSET_CACHE["clicksfx"]

    @property
    def shortclicksfx(self):
        return _ASSET_CACHE["shortclicksfx"]

    def _load_assets_async(self):
        try:
            loader_assets = Loader("cutscenes/assets")
            loader_parent = Loader("cutscenes/assets/parent_yell")

            hand = pygame.image.load(loader_assets.load("handplaceholder.png")).convert_alpha()

            try:
                clicksfx = pygame.mixer.Sound(loader_parent.load("horror_stinger.wav"))
                shortclicksfx = pygame.mixer.Sound(loader_parent.load("klik_short.wav"))
            except Exception:
                clicksfx = pygame.mixer.Sound(loader_parent.load("klik.wav"))
                shortclicksfx = pygame.mixer.Sound(loader_parent.load("klik_short.wav"))
                
            goreimgs = []
            for i in range(6):
                img = pygame.image.load(loader_parent.load(f"gore_img_{i+1}.png")).convert_alpha()
                goreimgs.append(img)

            with _CACHE_LOCK:
                _ASSET_CACHE["hand"] = hand
                _ASSET_CACHE["clicksfx"] = clicksfx
                _ASSET_CACHE["shortclicksfx"] = shortclicksfx
                _ASSET_CACHE["goreimgs"] = goreimgs
                _ASSET_CACHE["loaded"] = True
                _ASSET_CACHE["loading"] = False
        except Exception as e:
            print(f"[parent_yell] Error loading assets in background: {e}")
            with _CACHE_LOCK:
                _ASSET_CACHE["loading"] = False

    def _wait(self, timer_attr, seconds):
        current = getattr(self, timer_attr, 0.0)
        current += self.dt
        setattr(self, timer_attr, current)
        if current >= seconds:
            setattr(self, timer_attr, 0.0)
            return True
        return False

    @staticmethod
    def _approach(current, target, max_delta):
        if current < target:
            return min(current + max_delta, target)
        return max(current - max_delta, target)

    def goto_world(self):
        if self.itswarm:
            self.fade_t = 0
            self.loader.text_engine.start_text("", "")
            self.player.last_level = getattr(self.world, "current_level", None)
            self.world.change_level(0, self.player)
            self.player.apply_spawn_point(0)
            self.player.curr_animation = "sleep"
            self.player.dir = 0
            self.itswarm = False
            self.player.render_offset_x += 7

        #s
        self.fade_t = min(self.fade_t + self.dt / self.fade_duration, 1.0)
        self.fade_alpha = 255 - int(255 * pytweening.easeInQuad(self.fade_t))
        if self.fade_t >= 1.0:
            if self._wait("goto_world_wait", 4.5):
                return "YES"

    def trigger_trip_and_fall(self):
        s = self.goto_world_stage

        self.loader.text_engine.start_text("", "")

        if s == 1:
            # Shakes every single frame with the smallest possible non-zero displacement
            self.player.world_x = 303 + random.choice(self.shake_offsets_x)
            self.player.world_y = 142 + random.choice(self.shake_offsets_y)
            if self._wait("goto_world_wait", 3.5):
                self.player.world_x = 303.0
                self.player.world_y = 138.0
                self.goto_world_stage = 12

        elif s == 12:
            if self._wait("goto_world_wait", 0.5):
                print(f"x: {self.player.world_x}, y: {self.player.world_y}")
                self.player.world_x = 303.0
                self.player.world_y = 130.0
                self.player.animation_speed *= 2
                self.player.curr_animation = "Walking"
                self.player.dir = 1
                self.goto_world_stage = 2

        elif s == 2:
            self.player.world_x = self._approach(
                self.player.world_x, 160, self.player.speed / 2 * self.dt
            )
            if self.player.world_x <= 160:
                self.player.curr_animation = "Fall_ground"
                self.player.curr_frame = 0
                self.slide_start_x = self.player.world_x
                self.slide_t = 0.0
                self.goto_world_stage = 2.5

        elif s == 2.5:
            self.slide_t = min(self.slide_t + self.dt / self.slide_duration, 1)
            self.player.world_x = self.slide_start_x - self.slide_distance * pytweening.easeOutQuad(self.slide_t)
            if self.slide_t >= 1:
                self.goto_world_stage = 3

        elif s == 3:
            self.fade_t = min(self.fade_t + self.dt / self.fade_duration, 1.0)
            self.fade_alpha = int(255 * pytweening.easeInQuad(self.fade_t))
            if self.fade_t >= 1.0:
                self.goto_world_stage = 4

        elif s == 3.25:
            if self._wait("goto_world_wait", 1.5):
                self.goto_world_stage = 13

        elif s == 13:
            if self.FREEDOMTIMER <= 1:
                self.radius_offset = 2000 - (pytweening.easeInQuad(self.FREEDOMTIMER) * (2000 - 1400))
                print(self.FREEDOMTIMER)
                self.FREEDOMTIMER += 0.1 * self.dt
            else:
                if self._wait("goto_world_wait", 1.5):
                    self.FREEDOMTIMER = 0
                    self.goto_world_stage = 3.5

        elif s == 3.5:
            self.radius_offset = 1400 - (pytweening.easeInQuad(self.FREEDOMTIMER) * (1400 - 1100))
            print(self.FREEDOMTIMER)
            self.FREEDOMTIMER += 1.4 * self.dt

        elif s == 4:
            if self._wait("goto_world_wait", .5):
                self.show_black_screen = True
                self.player.animation_speed /= 2
                self.player.last_level = getattr(self.world, "current_level", None)
                self.world.change_level(3, self.player)
                self.player.apply_spawn_point(3)
                self.show_black = True
                self.player.render_offset_x = 0
                self.fade_alpha = 0
                self.fade_t = 0.0
                self.goto_world_stage = 50

        elif s == 50:
            if self._wait("goto_world_wait", 4.0):
                self.goto_world_stage = 5
                self.show_black = False
                self.gore_timer = 0.0
                self.gore_index = 0
                self.gore_last_index = -1

        elif s == 5:
            self.total_frames_elapsed += 1
            duration = self.gore_frame_time * len(self.goreimgs) + self.last_gore_image_time if self.goreimgs else 0.2
            if self.gore_last_index == 5 and self.shortclicksfx is not None and self.total_frames_elapsed % 3 == 0: #Last frame
                pygame.mixer.Sound.play(self.shortclicksfx) # Every frame

                
            if self._wait("goto_world_wait", duration):
                # self.show_black_screen = False
                self.goto_world_stage = 6

        elif s == 6:
            pygame.quit()
            sys.exit()
            if self._wait("goto_world_wait", 2.0):
                self.player.curr_animation = "Idle"
                self.goto_world_stage = 7

        elif s == 7:
            return "YES"

    def kill_music(self):
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
        self.fade_t = min(self.fade_t + self.dt / self.fade_duration, 1.0)
        self.fade_alpha = int(255 * pytweening.easeInQuad(self.fade_t))
        if self.fade_t >= 1.0:
            return "YES"

    def draw_back(self, loader, surface):
        if self.goto_world_stage >= 3.25 and self.hand is not None:
            center_x = 643
            center_y = 614

            for i in range(3):
                angle = 360 / 3 * i + 45
                rad = math.radians(angle)

                x = center_x + self.radius_offset * math.cos(rad)
                y = center_y + self.radius_offset * math.sin(rad)

                rect = self.hand.get_rect()
                rect.center = (x, y)
                surface.blit(self.hand, rect.topleft)

        if self.show_black_screen:
            if not self.show_black and self.goreimgs:
                self.gore_timer += self.dt
                self.gore_index = min(
                    int(self.gore_timer / self.gore_frame_time),
                    len(self.goreimgs) - 1,
                )
                surface.blit(self.goreimgs[self.gore_index], (0, 0))

                if self.gore_index != self.gore_last_index:
                    self.gore_last_index = self.gore_index
                    if self.clicksfx is not None:
                        pygame.mixer.Sound.play(self.clicksfx)

            if self.show_black:
                surface.fill((0, 0, 0))

        if self.fade_alpha > 0:
            overlay = pygame.Surface(surface.get_size())
            overlay.fill((0, 0, 0))
            overlay.set_alpha(self.fade_alpha)
            surface.blit(overlay, (0, 0))
