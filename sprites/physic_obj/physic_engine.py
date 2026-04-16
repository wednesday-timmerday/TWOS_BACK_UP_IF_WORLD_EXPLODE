import pygame
import importlib
import math
import pymunk
import pymunk.pygame_util

# Toggle this to see the physics circle drawn on screen
DEBUG_HITBOX = True

def clamp(val, min_val, max_val):
    return max(min_val, min(val, max_val))

class PhysicEngine:
    def __init__(self, world_loader):
        self.object = None
        self.speed_x = 0
        self.speed_y = 0
        self.turn_speed = 0
        self.angle = 0
        self.res = 0.1
        self.world_loader = world_loader

    def add_collision_mask(self, mask):
        self.static_segments = []
        width, height = mask.get_size()


        downsample = 4

        for y in range(0, height, downsample):
            solid = False
            start_x = 0

            for x in range(0, width, downsample):
                if mask.get_at((x, y)):  
                    if not solid:
                        solid = True
                        start_x = x
                else:
                    if solid:
                        # end segment
                        seg = pymunk.Segment(
                            self.space.static_body,
                            (start_x, y),
                            (x, y),
                            5
                        )
                        seg.friction = 2.0
                        seg.elasticity = 0.0
                        self.space.add(seg)
                        self.static_segments.append(seg)
                        solid = False

            # if the row ended while still solid
            if solid:
                seg = pymunk.Segment(
                    self.space.static_body,
                    (start_x, y),
                    (width, y),
                    5
                )
                seg.friction = 2.0
                seg.elasticity = 0.0
                self.space.add(seg)
                self.static_segments.append(seg)

        print("[PhysicEngine] Built ground from mask:", len(self.static_segments), "segments")



    def start_physic_obj(self, name_obj, player, collision_mask=None, spawn_x=None, spawn_y=None):
        self.object = importlib.import_module(f"sprites.physic_obj.{name_obj}.{name_obj}").PhysicObject(self.world_loader)

        self.object_image = self.object.original_image

        # Derive size from the ACTUAL image, not any hardcoded value.
        # This guarantees the hitbox always matches what you see.
        actual_w, actual_h = self.object_image.get_size()
        self.obj_w = actual_w
        self.obj_h = actual_h
        print(f"[PhysicEngine] '{name_obj}' image={actual_w}x{actual_h}")

        self.space = pymunk.Space()
        self.space.gravity = 0, 1500
        self.mass = self.object.mass

        # Circle radius = half the image width
        self.phys_radius = actual_w // 2
        self.moment = pymunk.moment_for_circle(self.mass, 0, self.phys_radius)
        self.body = pymunk.Body(self.mass, self.moment)

        # If spawn position given, use it immediately so there is NEVER a
        # one-frame ghost at start_x/start_y before load_enemies corrects it.
        if spawn_x is not None and spawn_y is not None:
            self.body.position = (spawn_x, spawn_y)
            self.object.world_x = spawn_x
            self.object.world_y = spawn_y
        else:
            self.body.position = (self.object.start_x, self.object.start_y)

        self.shape = pymunk.Circle(self.body, self.phys_radius)
        self.shape.friction = 1.0
        self.shape.elasticity = 0.1
        self.space.add(self.body, self.shape)
        print(f"[PhysicEngine] Circle radius={self.phys_radius}px")

        self.player_mass = player.mass
        self.player_body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
        self.player_body.position = player.world_x + player.rect.width / 2, player.world_y + player.rect.height / 2
        # Use hit_box size, not sprite rect — sprite rect is much larger than actual collision area
        self.player_shape = pymunk.Poly.create_box(self.player_body, (player.hit_box.width, player.hit_box.height))
        self.player_shape.friction = 1.0
        self.space.add(self.player_body, self.player_shape)
        
        # Add collision mask if provided
        if collision_mask is not None:
            self.add_collision_mask(collision_mask)

    def update(self, dt, player):

        self.object.check_triggers()
        if not self.object:
            return

        # Player lives in mini-res screen space (world_x ~= 303).
        # Orb lives in scrolling world space (world_x ~= 865).
        # Convert player to world space by adding cam_x.
        cam_x = getattr(self.world_loader, 'cam_x', 0)
        cam_y = getattr(self.world_loader, 'cam_y', 0)
        p_world_x = player.world_x + cam_x
        p_world_y = player.world_y + cam_y
        p_w = player.hit_box.width
        p_h = player.hit_box.height
        p_left  = p_world_x + player.hitbox_offset_x
        p_top   = p_world_y + player.hitbox_offset_y

        # Keep pymunk player body in sync using world-space coords
        self.player_body.position = p_left + p_w / 2, p_top + p_h / 2

        # Apply forces to the object based on its logic
        force_x, force_y = self.object.get_forces(player)
        self.body.velocity = (force_x, force_y)

        substeps = 5
        sub_dt = dt / substeps
        for _ in range(substeps):
            self.space.step(sub_dt)

        # Update object's position and angle
        self.object.world_x, self.object.world_y = self.body.position
        self.object.angle = math.degrees(self.body.angle)

        try:
            r = self.phys_radius

            # Circle (orb) vs AABB (player hitbox), both in world space
            closest_x = max(p_left, min(self.object.world_x, p_left + p_w))
            closest_y = max(p_top,  min(self.object.world_y, p_top  + p_h))
            dx = self.object.world_x - closest_x
            dy = self.object.world_y - closest_y
            dist_sq = dx * dx + dy * dy

            # Print every 60 frames so we can see what coords are being compared
            self._debug_tick = getattr(self, '_debug_tick', 0) + 1
            if self._debug_tick % 60 == 0:
                print(f"[PHYS] orb=({self.object.world_x:.1f},{self.object.world_y:.1f})  "
                      f"player_screen=({player.world_x:.1f},{player.world_y:.1f})  "
                      f"cam=({cam_x:.1f},{cam_y:.1f})  "
                      f"p_left={p_left:.1f} p_top={p_top:.1f} p_w={p_w} p_h={p_h}  "
                      f"dist={dist_sq**0.5:.1f}  r={r}")

            if dist_sq < r * r:
                sign = 1 if (self.object.world_x - (p_left + p_w / 2)) >= 0 else -1
                if sign > 0:
                    new_x = p_left + p_w + r + 1
                else:
                    new_x = p_left - r - 1
                self.body.position = (new_x, self.body.position.y)
                self.body.velocity = (sign * 150, self.body.velocity.y)
                self.object.world_x, self.object.world_y = self.body.position
        except Exception as e:
            print("[PHYS] collision error:", e)
            import traceback; traceback.print_exc()

    def draw(self, screen, world_x, world_y):
        if not self.object:
            return

        # World-to-screen: all coords are in mini-res (320x180) space
        cx = int(self.object.world_x - world_x)
        cy = int(self.object.world_y - world_y)

        # Nearest-neighbor rotate keeps pixel art crisp without upscaling
        rotated_image = pygame.transform.rotate(self.object_image, -self.object.angle)
        new_rect = rotated_image.get_rect(center=(cx, cy))
        screen.blit(rotated_image, new_rect.topleft)

        # DEBUG: draw the actual pymunk circle hitbox
        # Green circle = collision boundary, Red dot = body center
        if DEBUG_HITBOX:
            pygame.draw.circle(screen, (0, 255, 0), (cx, cy), self.phys_radius, 1)
            pygame.draw.circle(screen, (255, 0, 0), (cx, cy), 1)