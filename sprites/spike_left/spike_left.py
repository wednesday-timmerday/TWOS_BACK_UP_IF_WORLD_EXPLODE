from sprites.base_enemy import EnemyBase
from sprites.object_state import StateSerializable
import pygame

class spike_left(StateSerializable, EnemyBase):
    def __init__(self, player, world):
        StateSerializable.__init__(self)
        EnemyBase.__init__(self, "spike_left", frame_count=2, scale_percentage=(100,100))
        self.object_type = "spike_left"
        self.world_x = 400  # Initial position
        self.world_y = 300
        self.pos = [self.world_x, self.world_y]
        self.player = player
        self.world = world

    def serialize_state(self):
        """Save spike state including frame (blood status)"""
        return {
            "x": int(self.world_x),
            "y": int(self.world_y),
            "frame": int(self.current_frame),
        }
    
    def deserialize_state(self, state):
        """Restore spike state including frame"""
        self.world_x = state.get("x", 400)
        self.world_y = state.get("y", 300)
        self.pos = [self.world_x, self.world_y]
        self.current_frame = state.get("frame", 0)

    def draw_in_world(self, surface, cam_x, cam_y):
        """Draw spike in world coordinates"""

        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y

        frame = self.frames[self.current_frame]
        world_rect = frame.get_rect(midbottom=(self.world_x, self.world_y))

        if pygame.Rect.colliderect(world_rect, self.player.hit_box):
            self.player.die(self.world)
            self.current_frame = 1
        try:
            self.blit_frame_from_atlas(surface, self.current_frame, (screen_x - self.frames[self.current_frame].get_width()//2, screen_y - self.frames[self.current_frame].get_height()))
        except Exception:
            frame = self.frames[self.current_frame]
            rect = frame.get_rect(midbottom=(screen_x, screen_y))
            print(f"Collision: {pygame.Rect.colliderect(rect, self.player.get_rect())}")
            surface.blit(frame, rect)

    def draw(self, surface, x, y):
        frame = self.frames[self.current_frame]
        try:
            self.blit_frame_from_atlas(surface, self.current_frame, (x - frame.get_width()//2, y - frame.get_height()))
        except Exception:
            rect = frame.get_rect(midbottom=(x, y))
            surface.blit(frame, rect)
        
