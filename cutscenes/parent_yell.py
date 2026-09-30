import pygame
import random
from assetsLoader import Loader
import pytweening
import math


class cutscene:

    def __init__(self, player, world, loader):
        self.dialogue_id = "parent_yell"
        self.player = player
        self.world = world
        self.loader = loader
        self.dt = 0
        self.FREEDOMTIMER = 0

        self.x_offset_range = 1
        self.y_offset_range = 1

        self.show_black_screen = False

        self.goto_world_stage = 1
        self.goto_world_wait = 0.0

        self.slide_t = 0.0
        self.slide_start_x = 0
        self.slide_distance = 80
        self.slide_duration = 0.8
        self.show_black = True
        self.smile = pygame.image.load(Loader("cutscenes/assets").load("smile.png"))
        self.hand = pygame.image.load(Loader("cutscenes/assets").load("handplaceholder.png"))

        self.radius_offset = 2500

        self.goreimgs = []
        for i in range(6):
            img = pygame.image.load(Loader("cutscenes/assets/parent_yell").load(f"gore_img_{i+1}.png"))
            print(img)
            self.goreimgs.append(img)

        self.total_frames_per_gore = 2
        self.frame_counter = 0

        self.clicksfx = pygame.mixer.Sound(Loader("cutscenes/assets/parent_yell").load("klik.wav"))

        self.itswarm = True

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
            self.loader.text_engine.start_text("", "")
            self.player.last_level = getattr(self.world, "current_level", None)
            self.world.change_level(0, self.player)
            self.player.apply_spawn_point(0)
            self.player.curr_animation = "sleep"
            self.player.dir = 0
            self.itswarm = False
            
        if self._wait("goto_world_wait", 4.5):
            return "YES"

    def trigger_trip_and_fall(self):
        s = self.goto_world_stage

        self.loader.text_engine.start_text("", "") #Clear text

        if s == 1:
            self.player.world_x = 303 + random.randint(-self.x_offset_range, self.x_offset_range)
            self.player.world_y = 138 + random.randint(-self.y_offset_range, self.y_offset_range)
            if self._wait("goto_world_wait", 3.5):
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
            if self._wait("goto_world_wait", 0):
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
                self.goto_world_stage = 50
                
        elif s == 50:
            if self._wait("goto_world_wait", 0.75):
                self.goto_world_stage = 5
                self.show_black = False
                

        elif s == 5:
            if self._wait("goto_world_wait", 1 / 6 * self.total_frames_per_gore):
                self.show_black_screen = False
                self.goto_world_stage = 6

        elif s == 6:
            if self._wait("goto_world_wait", 2.0):
                self.player.curr_animation = "Idle"
                self.goto_world_stage = 7

        elif s == 7:
            return "YES"

    def kill_music(self):
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
        return "YES"

    def draw_back(self, loader, surface):
        if self.goto_world_stage >= 3.25:
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
            if random.randint(0, 3) == 4:
                surface.blit(self.smile, (0, 0))
            elif not self.show_black:
                surface.blit(self.goreimgs[math.floor(self.frame_counter / self.total_frames_per_gore)], (0, 0))
                if not math.floor(self.frame_counter / self.total_frames_per_gore) == 5:
                    self.frame_counter += 1

                if (self.frame_counter + 1) % self.total_frames_per_gore == 0:
                    print("yes")
                    pygame.mixer.Sound.play(self.clicksfx)

            if self.show_black:
                surface.fill((0, 0, 0))