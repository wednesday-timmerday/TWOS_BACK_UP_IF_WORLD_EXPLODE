class cutscene:

    def __init__(self, player, world, loader):

        self.dialogue_id = "tutor_r8_killed_dummy"

        self.player = player

        self.world = world

        self.loader = loader

        self.dt = 0
        
        self.mrtutor = next(

            (e for e in world.enemies if e.__class__.__name__.lower() == "mrtutor"),

            None

        )



    @staticmethod

    def _approach(current, target, max_delta):

        if current < target:

            return min(current + max_delta, target)

        return max(current - max_delta, target)


    def lock_player(self):
        self.player.can_move = False
        return "YES"

    def move_offscreen(self):
        # Move tutor off-screen
        self.loader.text_engine.start_text("","")

        target_x = self.player.world_x + 360/2+50

        self.mrtutor.world_x = self._approach(

            self.mrtutor.world_x,

            target_x,

            240 * self.dt

        )

        if self.mrtutor.world_x >= target_x:

            return "YES"

    def teleport_to_void(self):
        self.mrtutor.world_x = 999999
        return "YES"


    def angle_player(self):
        self.player.dir = 0 #Left aint right
        return "YES"
    
    def fight(self):
        if self.player.start_encounter("dummy") == 1:
            print("s")
            return "YES"