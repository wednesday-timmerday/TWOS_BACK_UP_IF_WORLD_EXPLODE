class cutscene:

    def __init__(self, player, world, loader):

        self.dialogue_id = "tutor_r7_2"
        self.player = player
        self.world = world
        self.loader = loader
        self.dt = 0
        world.actually_show_timer = False # disable timer rendering
        world.time_to_timer = 9999999999999999999999999999999999999999999999999999999999999 #istg if someone walks for this long ima lose it


        self.mrtutor = next(

            (e for e in world.enemies if e.__class__.__name__.lower() == "mrtutor"),

            None

        )



    @staticmethod

    def _approach(current, target, max_delta):

        if current < target:

            return min(current + max_delta, target)

        return max(current - max_delta, target)



    def goto_level_only_tutor_yes_no_maybe(self):
        # Move tutor off-screen
        self.loader.text_engine.start_text("","")

        target_x = 950

        self.mrtutor.world_x = self._approach(

            self.mrtutor.world_x,

            target_x,

            240 * self.dt

        )

        if self.mrtutor.world_x >= target_x:

            return "YES"
