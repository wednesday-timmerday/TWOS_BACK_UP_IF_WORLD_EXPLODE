import pygame

class Interactable:
    def __init__(self, player, world, loader):
        self.dialogue_id = "q_gate_r1"
        self.player = player
        self.world = world

    def switch_room(self):
        print("MMMMM")
        self.player.last_level = getattr(self.world, "current_level", None)
        self.world.change_level(1, self.player)
        self.player.apply_spawn_point(1)
        return "YES"
