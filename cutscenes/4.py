import pygame

class cutscene:
    def __init__(self, player, world, loader):
        self.dialogue_id = "4"
        self.player = player
        self.world = world
        self.loader = loader
        self.dt = 0
        self.jump_stage = 0
        self.jump_wait = 0.0
        self.mrtutor = next(
            (e for e in world.enemies if e.__class__.__name__.lower() == "mrtutor"),
            None
        )

    @staticmethod
    def _approach(current, target, max_delta):
        if current < target:
            return min(current + max_delta, target)
        return max(current - max_delta, target)

    
    def _wait(self, timer_attr, seconds):
        """Accumulate dt on a named timer. Returns True when elapsed."""
        current = getattr(self, timer_attr, 0.0)
        current += self.dt
        setattr(self, timer_attr, current)
        if current >= seconds:
            setattr(self, timer_attr, 0.0)
            return True
        return False


    
    def jump(self):
        s = self.jump_stage
        self.player.image = pygame.transform.flip(self.player.image, False, True)
        print(self.player.world_y)

        if s == 0:
            print(pygame.mouse.get_pos()[0]/ 4, pygame.mouse.get_pos()[1]/ 4)
            print(self.player.world_x, self.player.world_y)
            self.jump_stage += 1
            self.player.animation_speed *= 2
            self.player.curr_animation = "Walking"

        elif s == 1:
            self.player.world_x = self._approach(
                self.player.world_x, 290, self.player.speed / 4 * self.dt
            )
            if self.player.world_x >= 290: 
                self.player.curr_animation = "Idle"
                self.player.speed = 0.0
                self.jump_stage += 1
        
        elif s == 2:
            if self._wait("jump_wait", 1.5):
                self.player.curr_animation = "Dive"
                self.jump_stage += 1


        elif s == 3:
            self.player.world_y = self._approach(
                    self.player.world_y, 140, self.player.speed + 90.0 * self.dt
            )
            print(len(self.player.animations["Dive"]), self.player.curr_frame)
            if self.player.curr_frame == len(self.player.animations["Dive"]) - 1:
                self.player.curr_animation = "Fall"

            if self.player.world_y >= 140:
                self.player.curr_animation = "Idle"
                self.player.animation_speed /= 2
                self.player.speed = 90.0
                return "YES"
            
    def move_tutor(self):
        if self._wait("jump_wait", 1):
            return "YES"

    def really_move_tutor(self):
        target_x = self.player.world_x - 60
        self.mrtutor.world_x = self._approach(
            self.mrtutor.world_x,
            target_x,
            240 * self.dt
        )

        if abs(self.mrtutor.world_x - target_x) <= 0.5:
            return "YES"

