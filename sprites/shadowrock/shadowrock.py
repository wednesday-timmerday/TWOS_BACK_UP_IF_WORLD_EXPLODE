from sprites.base_enemy import EnemyBase

class ShadowRock(EnemyBase):
    def __init__(self):
        super().__init__("ShadowRock", frame_count=2, scale_percentage=(100,100))
        self.world_x = 400  # Initial position
        self.world_y = 300
        self.pos = [self.world_x, self.world_y]                                                                                          

    def draw_in_world(self, surface, cam_x, cam_y):
        """Draw ShadowRock in world coordinates"""
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        try:
            self.blit_frame_from_atlas(surface, self.current_frame, (screen_x - self.frames[self.current_frame].get_width()//2, screen_y - self.frames[self.current_frame].get_height()))
        except Exception:
            frame = self.frames[self.current_frame]
            rect = frame.get_rect(midbottom=(screen_x, screen_y))
            surface.blit(frame, rect)

    def draw(self, surface, x, y):
        frame = self.frames[self.current_frame]
        try:
            self.blit_frame_from_atlas(surface, self.current_frame, (x - frame.get_width()//2, y - frame.get_height()))
        except Exception:
            rect = frame.get_rect(midbottom=(x, y))
            surface.blit(frame, rect)
        