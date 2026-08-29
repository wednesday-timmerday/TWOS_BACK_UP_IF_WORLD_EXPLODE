from sprites.base_enemy import EnemyBase

from sprites.object_state import StateSerializable

import pygame
import math


class Btn_E(StateSerializable, EnemyBase):

    def __init__(self):

        StateSerializable.__init__(self)

        EnemyBase.__init__(self, "btn_e", frame_count=1, scale_percentage=(100,100))

        self.object_type = "btn_e"

        self.world_x = 400  # Initial position

        self.world_y = 300

        self.pos = [self.world_x, self.world_y]

        self.alpha = 0
        self.state = 0

    def serialize_state(self):

        """Save shadowrock state including animation frame"""

        return {

            "x": int(self.world_x),

            "y": int(self.world_y),

            "frame": int(self.current_frame),

        }

    

    def deserialize_state(self, state):

        """Restore shadowrock state including animation frame"""

        self.world_x = state.get("x", 400)

        self.world_y = state.get("y", 300)

        self.pos = [self.world_x, self.world_y]

        self.current_frame = state.get("frame", 0)                                                                                          



    def draw_in_world(self, surface, cam_x, cam_y):
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
    
        # Floating bob: ±4px, one cycle per ~1.5 seconds
        bob = math.sin(pygame.time.get_ticks() * 0.004) * 4
        screen_y += bob
    
        try:
            self.blit_frame_from_atlas(surface, self.current_frame, (screen_x - self.frames[self.current_frame].get_width()//2, screen_y - self.frames[self.current_frame].get_height()), self.alpha)
        except Exception:
            frame = self.frames[self.current_frame]
            rect = frame.get_rect(midbottom=(screen_x, screen_y))
            frame.fill((255,255,255,self.alpha), None, pygame.BLEND_RGBA_MULT)
            surface.blit(frame, rect)



    def draw(self, surface, x, y):


        frame = self.frames[self.current_frame]

        try:

            self.blit_frame_from_atlas(surface, self.current_frame, (x - frame.get_width()//2 + self.ox, y - frame.get_height() + self.oy))

        except Exception:

            rect = frame.get_rect(midbottom=(x, y))

            frame.fill((255,255,255,self.alpha), None, pygame.BLEND_RGBA_MULT)

            surface.blit(frame, rect)

        

