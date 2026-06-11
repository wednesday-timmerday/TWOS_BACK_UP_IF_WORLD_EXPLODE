import pygame
import random
from assetsLoader import Loader



class cutscene:

    def __init__(self, player, world, loader):

        self.dialogue_id = "parent_yell"

        self.player = player

        self.world = world

        self.loader = loader

        self.dt = 0



        self.show_black_screen = False



        # Per-function stage counters

        self.goto_world_stage = 0

        self.goto_world_wait = 0.0

        self.smile = pygame.image.load(Loader("cutscenes/assets").load("smile.png"))

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
            self.player.mouse_flag = True
            pygame.mouse.set_visible(True)
            print(pygame.mouse.get_pos()[0])
            pygame.mouse.set_pos( self._approach(pygame.mouse.get_pos()[0], 160, 200 * self.dt), 720/2)
            # self.player.world_x = self._approach(

            #     self.player.world_x, 160, self.player.speed / 2 * self.dt

            # )

            if self.player.world_x <= 160:

                self.player.curr_animation = "Idle"

                self.goto_world_stage += 1



        elif s == 3:

            if self._wait("goto_world_wait", 3.5):

                self.player.curr_animation = "Fall_ground"

                self.player.curr_frame = 0

                self.goto_world_stage += 1



        elif s == 4:

            if self._wait("goto_world_wait", 4.5):

                self.show_black_screen = True

                self.player.animation_speed /= 2

                self.player.last_level = getattr(self.world, "current_level", None)

                self.world.change_level(3, self.player)

                self.player.apply_spawn_point(3)

                self.goto_world_stage += 1



        elif s == 5:

            if self._wait("goto_world_wait", 2.0):

                self.show_black_screen = False

                self.goto_world_stage += 1



        elif s == 6:

            if self._wait("goto_world_wait", 2.0):

                self.player.curr_animation = "Idle"

                self.goto_world_stage += 1



        elif s == 7:

            return "YES"



    # ------------------------------------------------------------------



    def draw_back(self, loader, surface):

        if self.show_black_screen:
            if random.randint(0, 6666) == 231: #We should change these chances... eh fuck it
                surface.blit(self.smile, (0, 0))
            else:
                pygame.draw.rect(
    
                    surface, (0, 0, 0),
    
                    (0, 0, surface.get_width(), surface.get_height())
    
                )

