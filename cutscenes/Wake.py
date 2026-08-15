from assetsLoader import Loader

import pygame 
import pytweening
import random



class cutscene:

    def __init__(self, player, world, loader):

        self.dialogue_id = "Wake"

        self.player = player
        self.world = world
        self.loader = loader

        self.dt = 0

        self.music_loader = Loader("music")

        self.music_path = self.music_loader.load("static.ogg")
        self.music2_path = self.music_loader.load("Ambience 01.ogg")

        pygame.mixer.music.load(self.music_path)
        pygame.mixer.music.play(-1)

        self.play_cutscene_stage = 0
        self.play_cutscene_wait = 0.0
        self.vol_timer = 0.0

        self.before_vol = pygame.mixer.music.get_volume()

        self.render_hand = True

    def _wait(self, seconds):

        self.play_cutscene_wait += self.dt

        if self.play_cutscene_wait >= seconds:

            self.play_cutscene_wait = 0.0

            return True

        return False

    def play_cutscene(self):
        s = self.play_cutscene_stage

        if s == 0:

            self.player.bg_music_name = "Ambience 01.ogg"

            self.player.curr_frame = 0
            self.player.animation_timer = 0.0

            self.player.can_move = False

            self.player.curr_animation = "sleep"

            self.world._player_light_radius = 20

            self.vol_timer = 0.0

            self.before_vol = pygame.mixer.music.get_volume()

            pygame.mixer.music.set_volume(0)

            self.play_cutscene_stage = 1

            self.hand_y = -2000

            self.handpath = Loader("cutscenes/assets").load("handplaceholder.png")

            self.hand = pygame.image.load(self.handpath)

            self.hand = pygame.transform.rotate(self.hand, -90)

        elif s == 1:


            if self._wait(1):

                self.vol_timer = 0.0
                self.play_cutscene_stage = 2

        elif s == 2:

            volume = pytweening.easeInOutPoly(self.vol_timer)

            pygame.mixer.music.set_volume(volume)

            self.vol_timer += 0.05 * self.dt

            self.hand_y = -2000 + volume * 580

            if volume >= 0.95:


                pygame.mixer.music.stop()

                if self._wait(0.0): #Change endtimimg

                    self.vol_timer = 0

                    self.play_cutscene_stage = 7

        elif s == 7:
            if self.vol_timer <= 1:

                print(self.hand_y)

                self.hand_y = -1449 + -pytweening.easeInSine(self.vol_timer * 2) * 580
                self.world._player_light_radius = 20 + pytweening.easeInCirc(self.vol_timer) * 120
    
                self.vol_timer += 0.7 * self.dt 
            else:
                pygame.mixer.music.load(self.music2_path)
                pygame.mixer.music.set_volume(self.before_vol)
                pygame.mixer.music.play(-1)
                if self._wait(1.5):
                    self.play_cutscene_stage = 3

        elif s == 3:
            print("4")

            self.player.curr_animation = "Idle"

            if (
                hasattr(self.player, "_triggered_once")
                and hasattr(self, "trigger_idx")
            ):
                self.player._triggered_once.add(
                    self.trigger_idx
                )

            self.player.can_move = True
            self.player.incutscene = False

            self.play_cutscene_stage = 4

        elif s == 4:

            return "YES"

    def draw_back(self, loader, surface):
        if self.render_hand:
            x = 1150 + random.randint(-1, 1)
            surface.blit(self.hand, (x, self.hand_y))