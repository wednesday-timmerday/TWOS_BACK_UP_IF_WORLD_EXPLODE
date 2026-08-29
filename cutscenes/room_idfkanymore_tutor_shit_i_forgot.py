class cutscene:
    def __init__(self, player, world, loader):
        self.dialogue_id = "room_idfkanymore_tutor_shit_i_forgot"
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

    def Move_to_end(self):
        self.loader.text_engine.start_text("","")
        target_x = 420
        self.mrtutor.world_x = self._approach(
            self.mrtutor.world_x,
            target_x,
            240 * self.dt
        )
        if self.mrtutor.world_x >= target_x:
            return "YES"
