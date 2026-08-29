import pygame

def run(cutscene, dt, player, world, joystick, event):

    def z_pressed():
        return pygame.key.get_pressed()[pygame.K_z] or joystick.get_button(0) or pygame.key.get_pressed()[pygame.K_y]
    if not hasattr(cutscene, "step"):
        cutscene.step = 0

    if joystick is None:
        class DummyJoy:
            def get_button(self, i): return False
            def get_axis(self, i): return 0
        joystick = DummyJoy()
    if cutscene.step == 0:
        if z_pressed():
            cutscene.step = 1
        return

    if cutscene.step == 1:
        player.curr_animation = "Idle"
        player.curr_frame = 0
        player.can_move = False
        cutscene.text_engine.start_text(
            "* There is a monster somewhere here",
            ""
        )
        cutscene.step = 2
    elif cutscene.step == 2:
        cutscene.text_engine.update(dt)

        if cutscene.text_engine.finished and z_pressed():
            player.can_move = True
            cutscene.running = False
