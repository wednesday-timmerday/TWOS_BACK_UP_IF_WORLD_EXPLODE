class cutscene:

    def __init__(self, player, world, loader):

        self.dialogue_id = "tutor_r8_1"

        self.player = player

        self.world = world

        self.loader = loader

        self.dt = 0

    def angle_player(self):
        self.player.dir = 0 #Left aint right
        return "YES"
    
    def fight(self):
        self.loader.text_engine.start_text("", "") #Clear txt
        if self.player.start_encounter("dummy", self.loader.trigger_idx) == 1:
            return "YES"