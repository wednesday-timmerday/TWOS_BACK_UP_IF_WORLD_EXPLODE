from sprites.base_enemy import EnemyBase
from sprites.object_state import StateSerializable
import pygame   

class MrTutor(StateSerializable, EnemyBase):
    def __init__(self):
        StateSerializable.__init__(self)
        EnemyBase.__init__(self, "MrTutor", frame_count=1, scale_percentage=(100, 100))
        self.object_type = "mrtutor"
        self.world_x = 400  # Initial position
        self.world_y = 300
        self.pos = [self.world_x, self.world_y]
    
    def serialize_state(self):
        """Save MrTutor state including position"""
        return {
            "x": int(self.world_x),
            "y": int(self.world_y),
        }
    
    def deserialize_state(self, state):
        """Restore MrTutor state including position"""
        self.world_x = state.get("x", 400)
        self.world_y = state.get("y", 300)
        self.pos = [self.world_x, self.world_y]                                                                                          

    def draw_in_world(self, surface, cam_x, cam_y):
        # MrTutor uses a simple rectangle, nothing to atlas here â€” still draw quickly
        color = (255,0,0)
        surface.fill(color, pygame.Rect(self.world_x - cam_x, self.world_y - cam_y, 15,30   ))

    def draw(self, surface, x, y):
        frame  = pygame.Rect(self.world_x - x, self.world_y - y, 50, 100)
        color = (255,0,0)
        pygame.draw.rect(surface, color, pygame.Rect(self.world_x - x, self.world_y - y, 15,30)) 
        
