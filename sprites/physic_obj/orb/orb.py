import pygame
import math
from assetsLoader import Loader
from sprites.object_state import StateSerializable
import json
import os


def load_json_level_spec():
    level_spec_path = Loader("worlds").load("level-spec.json")
    if level_spec_path and os.path.exists(level_spec_path):
        with open(level_spec_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


class PhysicObject(StateSerializable):
    def __init__(self, world_loader):
        StateSerializable.__init__(self)
        self.world_loader = world_loader
        self.object_type = "orb"  # For state management

        # Image â€” load first so width/height come from actual sprite
        self.image_loader = Loader("sprites/physic_obj/orb/frames")
        self.image_path = self.image_loader.load("orb-1.png")
        self.original_image = pygame.image.load(self.image_path).convert_alpha()

        # Size â€” derived from the actual image, NOT hardcoded
        # This prevents the hitbox from being wrong relative to the sprite
        self.width, self.height = self.original_image.get_size()
        self.radius = self.width // 2
        self.angle = 0
        self._last_angle = None
        self.image = self.original_image
        self.rotated_image = self.original_image

        # Physics
        self.mass = 10
        # start_x/start_y are overridden by world_loader.load_enemies from level-spec.
        # These are just fallback defaults â€” they should never actually be used.
        self.start_x = 0
        self.start_y = 0

        self.world_x = self.start_x
        self.world_y = self.start_y

        # Level data
        self.level_spec = load_json_level_spec()
        self.hit_cutscene = False

        # Cache trigger rects
        self.cutscene_triggers = []
        self._load_cutscene_triggers()
        world_loader.add_light_source(self, 150)
    
    def serialize_state(self):
        """Save orb state including position and angle"""
        return {
            "x": int(self.world_x),
            "y": int(self.world_y),
            "angle": float(self.angle),
        }
    
    def deserialize_state(self, state):
        """Restore orb state including position and angle"""
        self.world_x = state.get("x", 0)
        self.world_y = state.get("y", 0)
        self.angle = state.get("angle", 0)


    # -----------------------------
    # TRIGGER SETUP
    # -----------------------------
    def _load_cutscene_triggers(self):
        level_key = f"level_{self.world_loader.current_level}"
        level_data = self.level_spec.get(level_key, {})
        triggers = level_data.get("triggers", [])

        for trigger in triggers:
            name = trigger.get("name", "").strip().lower()
            if name == "cutscene(2)":
                rect = pygame.Rect(
                    trigger.get("x", 0),
                    trigger.get("y", 0),
                    trigger.get("w", 0),
                    trigger.get("h", 0),
                )
                self.cutscene_triggers.append(rect)

    # -----------------------------
    # PHYSICS ONLY
    # -----------------------------
    def get_forces(self, player):
        dx = (player.world_x + player.rect.width / 2) - self.world_x
        dy = 0  # locked axis

        dist = abs(dx)
        if dist == 0:
            return 0, 0

        dx /= dist
        strength = 0  # placeholder for future physics

        return dx * strength, 0

    # -----------------------------
    # TRIGGER CHECK (SEPARATE)
    # -----------------------------
    def check_triggers(self):
        if self.hit_cutscene:
            return

        orb_center_x = self.world_x + self.radius
        orb_center_y = self.world_y + self.radius

        for rect in self.cutscene_triggers:
            # dichtstbijzijnde punt op de rectangle
            closest_x = max(rect.left, min(orb_center_x, rect.right))
            closest_y = max(rect.top, min(orb_center_y, rect.bottom))

            dx = orb_center_x - closest_x
            dy = orb_center_y - closest_y

            distance_squared = dx * dx + dy * dy

            if distance_squared <= self.radius * self.radius:
                self.hit_cutscene = True
                break

    # -----------------------------
    # ROTATION CACHE
    # -----------------------------
    def update_rotation(self):
        if self.angle != self._last_angle:
            self.rotated_image = pygame.transform.rotozoom(
                self.original_image, -self.angle, 1.0
            )
            self._last_angle = self.angle

    # -----------------------------
    # DRAW
    # -----------------------------
    def draw_in_world(self, screen, cam_x, cam_y):
        self.update_rotation()
        #self.check_triggers()

        debug_center = (
            int(self.world_x - self.radius + cam_x),
            int(self.world_y - self.radius + cam_y),
        )

        rect = self.rotated_image.get_rect(
            center=(self.world_x - cam_x, self.world_y - cam_y)
        )
        screen.blit(self.rotated_image, rect.topleft)

