from sprites.base_enemy import EnemyBase
from sprites.object_state import StateSerializable

class blobtigoo(StateSerializable, EnemyBase):
    def __init__(self, scale_percentage=(100,100)):
        StateSerializable.__init__(self)
        EnemyBase.__init__(self, "blobtigoo", frame_count=2, scale_percentage=scale_percentage)
        self.object_type = "blobtigoo"
        self.world_x = 400  # Initial position
        self.world_y = 300
        self.pos = [self.world_x, self.world_y]
    
    def serialize_state(self):
        """Save blobtigoo state including animation frame"""
        return {
            "x": int(self.world_x),
            "y": int(self.world_y),
            "frame": int(self.current_frame),
        }
    
    def deserialize_state(self, state):
        """Restore blobtigoo state including animation frame"""
        self.world_x = state.get("x", 400)
        self.world_y = state.get("y", 300)
        self.pos = [self.world_x, self.world_y]
        self.current_frame = state.get("frame", 0)                                                                                          

    def draw_in_world(self, surface, cam_x, cam_y):
        """Draw blobtigoo in world coordinates"""
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
        
