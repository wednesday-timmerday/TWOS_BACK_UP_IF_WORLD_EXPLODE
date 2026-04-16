from sprites.base_enemy import EnemyBase
import pygame   

class wdcibles(EnemyBase):
    def __init__(self):
        super().__init__("wdcibles", frame_count=1, scale_percentage=(325, 325))
        self.world_x = 400  # Initial position
        self.world_y = 300
        self.pos = [self.world_x, self.world_y]                                                                                          

    def draw_in_world(self, surface, cam_x, cam_y):
        """Draw HammerOBJ in world coordinates"""
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        # use atlas blit when available
        try:
            self.blit_frame_from_atlas(surface, self.current_frame, (screen_x - self.frames[self.current_frame].get_width()//2, screen_y - self.frames[self.current_frame].get_height()))
        except Exception:
            frame = self.frames[self.current_frame]
            rect = frame.get_rect(midbottom=(screen_x, screen_y))
            surface.blit(frame, rect)
        