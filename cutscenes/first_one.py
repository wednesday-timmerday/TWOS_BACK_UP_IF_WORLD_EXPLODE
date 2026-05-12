import pygame
from assetsLoader import Loader

music_loader = Loader("music")
music_path = music_loader.load("Ambience 01.ogg")
pygame.mixer.music.load(music_path)
pygame.mixer.music.play(-1)
def run(cutscene, dt, player, world, joystick, event):
    def z_pressed():
        return pygame.key.get_pressed()[pygame.K_z] or joystick.get_button(0) or pygame.key.get_pressed()[pygame.K_y]

    def advance_wait(seconds):
        """Returns True if wait time has elapsed, else accumulates timer."""
        cutscene.wait_timer += dt
        if cutscene.wait_timer >= seconds:
            cutscene.wait_timer = 0.0
            return True
        return False
    if not hasattr(cutscene, "wait_timer"):
        cutscene.wait_timer = 0.0
    if not hasattr(cutscene, "step"):
        cutscene.step = 0
        player.curr_frame = 0
        player.animation_timer = 0.0
        player.can_move = False

    if joystick is None:
        class DummyJoy:
            def get_button(self, i): return False
            def get_axis(self, i): return 0
        joystick = DummyJoy()
    if cutscene.step == 0:
        player.curr_animation = "Fall_ground"
        if advance_wait(3.5):
            cutscene.step = 1
    
    elif cutscene.step == 1:
        player.curr_animation = "Idle"
        if hasattr(player, "_triggered_once") and hasattr(cutscene, "trigger_idx"):
            player._triggered_once.add(cutscene.trigger_idx)
        cutscene.running = False
        player.can_move = True


