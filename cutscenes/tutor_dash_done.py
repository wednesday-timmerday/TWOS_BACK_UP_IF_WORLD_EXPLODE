class cutscene:
    def __init__(self, player, world, loader):
        self.dialogue_id = "tutor_dash_done"
        self.player = player
        self.world = world
        self.loader = loader
        self.dt = 0