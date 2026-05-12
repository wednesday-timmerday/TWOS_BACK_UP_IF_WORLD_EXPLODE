from sprites.base_enemy import EnemyBase
from sprites.object_state import StateSerializable

class hammer(StateSerializable, EnemyBase):
    def __init__(self, world_loader=None):
        StateSerializable.__init__(self)
        EnemyBase.__init__(self, "hammer", frame_count=1, scale_percentage=(100, 100))
        self.object_type = "hammer"
        self.world_x = 400  # Initial position
        self.world_y = 300
        self.pos = [self.world_x, self.world_y]
        self.world_loader = world_loader
        self.world_loader.add_light_source(self, 550)
    
    def serialize_state(self):
        """Save hammer state including position and frame"""
        return {
            "x": int(self.world_x),
            "y": int(self.world_y),
            "frame": int(self.current_frame),
        }
    
    def deserialize_state(self, state):
        """Restore hammer state including position and frame"""
        self.world_x = state.get("x", 400)
        self.world_y = state.get("y", 300)
        self.pos = [self.world_x, self.world_y]
        self.current_frame = state.get("frame", 0)


    def draw_in_world(self, surface, cam_x, cam_y):
        """Draw hammer in world coordinates"""
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        try:
            self.blit_frame_from_atlas(surface, self.current_frame, (screen_x - self.frames[self.current_frame].get_width()//2, screen_y - self.frames[self.current_frame].get_height()))
        except Exception:
            frame = self.frames[self.current_frame]
            rect = frame.get_rect(midbottom=(screen_x, screen_y))
            surface.blit(frame, rect)
