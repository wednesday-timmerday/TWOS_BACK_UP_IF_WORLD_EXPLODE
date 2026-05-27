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
        if self.player.start_encounter("fight_mrtutor") == 1:
            print("s")
            return "YES"