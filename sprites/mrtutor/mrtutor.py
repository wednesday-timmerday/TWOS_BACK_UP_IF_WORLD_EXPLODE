from sprites.base_enemy import EnemyBase
import pygame   

class MrTutor(EnemyBase):
    def __init__(self):
        super().__init__("MrTutor", frame_count=1, scale_percentage=(100, 100))
        self.world_x = 400  # Initial position
        self.world_y = 300
        self.pos = [self.world_x, self.world_y]                                                                                          

    def draw_in_world(self, surface, cam_x, cam_y):
        # MrTutor uses a simple rectangle, nothing to atlas here — still draw quickly
        color = (255,0,0)
        surface.fill(color, pygame.Rect(self.world_x - cam_x, self.world_y - cam_y, 15,30   ))

    def draw(self, surface, x, y):
        frame  = pygame.Rect(self.world_x - x, self.world_y - y, 50, 100)
        color = (255,0,0)
        pygame.draw.rect(surface, color, pygame.Rect(self.world_x - x, self.world_y - y, 15,30)) 
        