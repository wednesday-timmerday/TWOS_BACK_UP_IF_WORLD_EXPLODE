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



        self.show_black_screen = False



        # Per-function stage counters

        self.goto_world_stage = 0

        self.goto_world_wait = 0.0

        self.smile = pygame.image.load(Loader("cutscenes/assets").load("smile.png"))

        self.hand = pygame.image.load(Loader("cutscenes/assets").load("handplaceholder.png"))

        self.radius_offset = 2500 #1000 is touchy

        self.goreimgs = []

        for i in range(6):
            img = pygame.image.load(Loader("cutscenes/assets/parent_yell").load(f"gore_img_{i+1}.png"))
            print(img)
            self.goreimgs.append(img)

        self.total_frames_per_gore = 3

        self.frame_counter = 0

        self.clicksfx = pygame.mixer.Sound(Loader("cutscenes/assets/parent_yell").load("klik.wav"))


    # ------------------------------------------------------------------

    # Helpers

    # ------------------------------------------------------------------



    def _wait(self, timer_attr, seconds):

        """Accumulate dt on a named timer. Returns True when elapsed."""

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

    

    # ------------------------------------------------------------------



    def goto_world(self):

        s = self.goto_world_stage

        if s == 0:

            self.loader.text_engine.start_text("", "")

            self.player.last_level = getattr(self.world, "current_level", None)


            self.world.change_level(0, self.player)

            self.player.apply_spawn_point(0)

            self.player.curr_animation = "sleep"

            self.player.dir = 0

            self.goto_world_stage += 1



        elif s == 1:

            if self._wait("goto_world_wait", 6.5):

                self.player.animation_speed *= 2

                self.player.curr_animation = "Walking"

                self.player.dir = 1

                self.goto_world_stage += 1



        elif s == 2:
            # self.player.mouse_flag = True
            # # pygame.mouse.set_visible(True)
            # # print(pygame.mouse.get_pos()[0])
            # # pygame.mouse.set_pos( self._approach(pygame.mouse.get_pos()[0], 160, 200 * self.dt), 720/2)
            self.player.world_x = self._approach(

                self.player.world_x, 160, self.player.speed / 2 * self.dt

            )

            if self.player.world_x <= 160:

                self.player.curr_animation = "Idle"

                self.goto_world_stage += 1



        elif s == 3:

            if self._wait("goto_world_wait", 3.5):

                self.player.curr_animation = "Fall_ground"

                self.player.curr_frame = 0

                self.goto_world_stage += 1

        elif s == 3.25:
            if self._wait("goto_world_wait", 1.5):
                self.goto_world_stage = 12

        elif s == 12:
            # Move the hands to 1200

            if self.FREEDOMTIMER <= 1:

                self.radius_offset = 2000 - (pytweening.easeInQuad(self.FREEDOMTIMER) * (2000-1400))
                print(self.FREEDOMTIMER)
                self.FREEDOMTIMER += 0.1 * self.dt # 5secs
            else:
                if self._wait("goto_world_wait", 1.5):
                    self.FREEDOMTIMER = 0
                    self.goto_world_stage = 3.5


        elif s == 3.5:
            # wait like 2.5 sec and move hands fast

            self.radius_offset = 1400 - (pytweening.easeInQuad(self.FREEDOMTIMER) * (1400-1100))
            print(self.FREEDOMTIMER)
            self.FREEDOMTIMER += 1.4 * self.dt # 0.7secs

            # #Might not even need this
            # if self.FREEDOMTIMER <= 1:
            #     self.world._player_light_radius = 100 - (pytweening.easeInQuad((self.FREEDOMTIMER)) * 80)
            #     self.FREEDOMTIMER += 0.5 * self.dt # 2secs
            # else:
            #     print("FU")


        elif s == 4:

            if self._wait("goto_world_wait", 4.5):


                self.show_black_screen = True

                self.player.animation_speed /= 2

                self.player.last_level = getattr(self.world, "current_level", None)

                self.world.change_level(3, self.player)

                self.player.apply_spawn_point(3)

                self.goto_world_stage += 1



        elif s == 5:

            if self._wait("goto_world_wait", 1/6*self.total_frames_per_gore):

                self.show_black_screen = False

                self.goto_world_stage += 1



        elif s == 6:

            if self._wait("goto_world_wait", 2.0):

                self.player.curr_animation = "Idle"

                self.goto_world_stage += 1



        elif s == 7:

            return "YES"


    # ------------------------------------------------------------------
     
    
    def kill_music(self):
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
        return "YES"



    # ------------------------------------------------------------------



    def draw_back(self, loader, surface):
        if self.goto_world_stage >= 3.25:

            # center_x = pygame.mouse.get_pos()[0]
            # center_y = pygame.mouse.get_pos()[1]

            # print(f"Mouse pos: {pygame.mouse.get_pos()}")

            center_x = 643
            center_y = 614

            for i in range(3):
                angle = 360 / 3 * i + 45
                rad = math.radians(angle)

                x = center_x + self.radius_offset * math.cos(rad)
                y = center_y + self.radius_offset * math.sin(rad)

                angle_correction = 180 
                pygame_angle = -angle + angle_correction

                img = self.hand

                rect = img.get_rect()
                rect.center = (x, y)

                surface.blit(img, rect.topleft)


        if self.show_black_screen:
            if random.randint(0, 3) == 4: #We should change these chances... eh fuck it
                surface.blit(self.smile, (0, 0))
            else:
                surface.blit(self.goreimgs[math.floor(self.frame_counter/self.total_frames_per_gore)], (0,0))
                if not math.floor(self.frame_counter/self.total_frames_per_gore) == 5:
                    self.frame_counter += 1 

                if (self.frame_counter + 1) % self.total_frames_per_gore == 0:
                    print("yes")
                    pygame.mixer.Sound.play(self.clicksfx)
