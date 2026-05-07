class cutscene:
    def __init__(self, player, world, loader):
        self.dialogue_id = "show_the_dashbtn_thingy"
        self.player = player
        self.world = world
        self.loader = loader
        self.dt = 0
        self.btn =  next(
            (e for e in world.enemies if e.__class__.__name__.lower() == "buttone"),
            None
        )
        print(f"aaaaaaaaaaaaAAAAAAAAAAAAAA {world.enemies}")
        if self.btn:
            print(f"Found btn_e: {self.btn}")
        else:
            print(f"btn_e not found. Enemy classes: {[e.__class__.__name__ for e in world.enemies]}")
        self.time = 0
        self.dur = 1.0
        self.old_y = self.btn.world_y
        self.state = 0
        self.next_triggered = False
    
    def ease_out_cubic(self, x: float) -> float:
        return 1 - (1 - x) ** 3
    
    def Tetoris(self):
        print(self.old_y)
        self.player.can_move = True
        self.time += self.dt
        t = min(self.time / self.dur, 1.0)
        ease = self.ease_out_cubic(t)

        self.btn.alpha = 0 + (255 - 0) * ease

        if self.state == 1:
            self.btn.world_y += 5 * self.dt
            if self.btn.world_y >= self.old_y + 2:
                self.state = 0
        else:
            self.btn.world_y -= 5 * self.dt
            if self.btn.world_y <= self.old_y - 2:
                self.state = 1
        
        # Trigger next cutscene once when animation completes, but keep running
        if t >= 1.0 and not self.next_triggered:
            self.next_triggered = True
            return "YES"