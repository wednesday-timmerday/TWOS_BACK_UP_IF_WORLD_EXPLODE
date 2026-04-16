from sprites.base_enemy import EnemyBase
import pygame   

class CoolEffect(EnemyBase):
    def __init__(self):
        super().__init__("CoolEffect", frame_count=1, scale_percentage=(325, 325))
        self.world_x = 400  # Initial position
        self.world_y = 300
        self.pos = [self.world_x, self.world_y]                                                                                          

    def draw_in_world(self, surface, cam_x, cam_y):
        frame  = pygame.Rect(self.world_x - cam_x, self.world_y - cam_y, 50, 100)
        surface.blit(surface, frame)

    def draw(self, surface, x, y):
        frame  = pygame.Rect(self.world_x - x, self.world_y - y, 50, 100)
        surface.blit(surface, frame)
        