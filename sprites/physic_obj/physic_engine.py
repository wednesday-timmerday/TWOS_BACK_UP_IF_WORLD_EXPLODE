import pygame
import importlib
import math
import pymunk
import pymunk.pygame_util

DEBUG_HITBOX = False

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
        self.object = importlib.import_module(
            f"sprites.physic_obj.{name_obj}.{name_obj}"
        ).PhysicObject(self.world_loader)

        self.object_image = self.object.original_image
        actual_w, actual_h = self.object_image.get_size()
        self.obj_w = actual_w
        self.obj_h = actual_h
        print(f"[PhysicEngine] '{name_obj}' image={actual_w}x{actual_h}")

        self.space = pymunk.Space()
        # 400 px/sÂ² feels natural at mini-res (320x180).
        # Previously 1500 was way too strong and tunnelled through floors.
        self.space.gravity = 0, 400

        self.mass = self.object.mass
        self.phys_radius = actual_w // 2

        # Solid circle moment â€” rolls naturally when it hits things
        self.moment = pymunk.moment_for_circle(self.mass, 0, self.phys_radius)
        self.body = pymunk.Body(self.mass, self.moment)

        if spawn_x is not None and spawn_y is not None:
            self.body.position = (spawn_x, spawn_y)
            self.object.world_x = spawn_x
            self.object.world_y = spawn_y
        else:
            self.body.position = (self.object.start_x, self.object.start_y)

        self.shape = pymunk.Circle(self.body, self.phys_radius)
        self.shape.friction   = 0.9   # high friction -> rolling when pushed
        self.shape.elasticity = 0.3   # slight bounce
        self.space.add(self.body, self.shape)

        # Damping: linear slows horizontal sliding, angular slows spinning.
        # Without these the orb rolls forever on a frictionless surface.
        self.space.damping = 0.70      # global velocity damping per second
        self.body.angular_damping = 0.97  # bleed off spin each frame
        print(f"[PhysicEngine] Circle radius={self.phys_radius}px")

        # Kinematic player body so pymunk can push the orb on contact
        self.player_body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
        self.player_body.position = (
            player.world_x + player.hitbox_offset_x + player.hit_box.width  / 2.0,
            player.world_y + player.hitbox_offset_y + player.hit_box.height / 2.0,
        )
        self.player_shape = pymunk.Poly.create_box(
            self.player_body,
            (player.hit_box.width, player.hit_box.height)
        )
        self.player_shape.friction   = 0.9
        self.player_shape.elasticity = 0.0
        self.space.add(self.player_body, self.player_shape)

        if collision_mask is not None:
            self.add_collision_mask(collision_mask)

    def update(self, dt, player):
        if not self.object:
            return

        self.object.check_triggers()

        # Player world_x/world_y are in the same world space as the orb.
        p_w    = player.hit_box.width
        p_h    = player.hit_box.height
        p_left = player.world_x + player.hitbox_offset_x
        p_top  = player.world_y + player.hitbox_offset_y

        # Sync kinematic player body to actual world position each frame
        self.player_body.position = p_left + p_w / 2.0, p_top + p_h / 2.0

        # DO NOT set body.velocity directly -- pymunk accumulates gravity automatically.
        # Only apply extra forces the object logic requests.
        force_x, force_y = self.object.get_forces(player)
        if force_x != 0 or force_y != 0:
            self.body.apply_force_at_local_point(
                (force_x * self.mass, force_y * self.mass), (0, 0)
            )

        # Step the simulation in small substeps for stability
        substeps = 5
        sub_dt = dt / substeps
        for _ in range(substeps):
            self.space.step(sub_dt)

        # Write physics result back to game object
        self.object.world_x, self.object.world_y = self.body.position
        self.object.angle = math.degrees(self.body.angle)

        # Bleed off angular velocity every frame so it actually stops spinning.
        # space.damping is per-second and too weak at high framerates.
        self.body.angular_velocity *= 0.85
        vx, vy = self.body.velocity
        self.body.velocity = (vx * 0.88, vy)  # horizontal drag only, don't touch vertical (gravity)

        # Manual circle-vs-AABB nudge as tunnelling safeguard.
        r         = self.phys_radius
        closest_x = max(p_left, min(self.object.world_x, p_left + p_w))
        closest_y = max(p_top,  min(self.object.world_y, p_top  + p_h))
        dx        = self.object.world_x - closest_x
        dy        = self.object.world_y - closest_y

        if dx * dx + dy * dy < r * r:
            sign  = 1 if (self.object.world_x >= p_left + p_w / 2.0) else -1
            new_x = (p_left + p_w + r + 1) if sign > 0 else (p_left - r - 1)
            self.body.position = (new_x, self.body.position.y)
            # Just give it a gentle fixed push â€” no impulse accumulation
            vx, vy = self.body.velocity
            push = sign * 60
            # Only apply push if orb isn't already moving away fast enough
            if abs(vx) < abs(push) or (vx * sign) < 0:
                self.body.velocity = (push, vy)
            self.object.world_x, self.object.world_y = self.body.position

    def draw(self, screen, world_x, world_y):
        if not self.object:
            return

        cx = int(self.object.world_x - world_x)
        cy = int(self.object.world_y - world_y)

        rotated_image = pygame.transform.rotate(self.object_image, -self.object.angle)
        new_rect = rotated_image.get_rect(center=(cx, cy))
        screen.blit(rotated_image, new_rect.topleft)

        if DEBUG_HITBOX:
            pygame.draw.circle(screen, (0, 255, 0), (cx, cy), self.phys_radius, 1)
            pygame.draw.circle(screen, (255, 0, 0), (cx, cy), 1)

