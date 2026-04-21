class Interactable:
    def __init__(self, player, world, loader):
        self.dialogue_id = "q_gate_r1_idfk"
        self.player = player
        self.world = world

    def switch_room(self):
        print("Butter")
        self.player.last_level = getattr(self.world, "current_level", None)
        self.world.change_level(5, self.player)
        self.player.apply_spawn_point(5)
        return "YES"