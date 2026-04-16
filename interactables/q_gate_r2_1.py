import pygame

# def run(cutscene, dt, player, world, joystick, event):

#     def z_pressed():
#         return pygame.key.get_pressed()[pygame.K_z] or joystick.get_button(0) or pygame.key.get_pressed()[pygame.K_y]
#     if not hasattr(cutscene, "step"):
#         cutscene.step = 0

#     if joystick is None:
#         class DummyJoy:
#             def get_button(self, i): return False
#             def get_axis(self, i): return 0
#         joystick = DummyJoy()
#     if cutscene.step == 0:
#         if z_pressed():
#             cutscene.step = 1
#         return

#     if cutscene.step == 1:
#         player.last_level = getattr(world, "current_level", None)
#         world.change_level(0, player)
#         player.apply_spawn_point(0)
#     elif cutscene.step == 2:
#         cutscene.text_engine.update(dt)

#         if cutscene.text_engine.finished and z_pressed():
#             player.can_move = True
#             cutscene.running = False

class Interactable:
    def __init__(self, player, world, loader):
        self.dialogue_id = "q_gate_r2_1"
        self.player = player
        self.world = world

    def switch_room(self):
        print("Butter")
        self.player.last_level = getattr(self.world, "current_level", None)
        self.world.change_level(0, self.player)
        self.player.apply_spawn_point(0)
        return "YES"