import pygame
import math
import random

"""
INFO DUMP TIME FOR FUTURE ME (its just me for tmr):

1. (UNUSED) The wall heights will be determined by a black and white image, where pure white = 0 and pure black = X (where X will be set in level_spec, just like type flag ("is_topdown": True/False))
2. We need to find a way to accuratly "muffle" the audio (if no direct rays to player, use these as audio)
3. We need to add echo (rebounce the rays with a 5-10% chance of despawning)
4. We need to add wall bounces (path like flips dir (- = +))
5. We need to find the AVG of all that reach the player, use the first bounce and use that as audio dir
5. (but more detail): We raytrace the audio till we hit the audio, then we go to the bounces, check the last one, take the AVG and thats the dir the audio should come from
"""

class AudioTracer:
    def __init__(self, screen):
        self.screen = screen
        self.walls = []
        self.rays = []
        self.blue_rays = []
        self.max_bounces = 10
        self.mx, self.my = 0, 0

    
    def spawn_wall(self, x, y, w, h):
        self.walls.append(pygame.Rect(x, y, w, h))

    def get_normal(self, rect, x, y):
        if abs(x - rect.left) < 1:
            return (-1, 0)
        if abs(x - rect.right) < 1:
            return (1, 0)
        if abs(y - rect.top) < 1:
            return (0, -1)
        if abs(y - rect.bottom) < 1:
            return (0, 1)
        return (0, 0)

    def shoot_single_ray(self, origin, direction_deg, bounce=0):
        if bounce > self.max_bounces:
            return

        ox, oy = origin

        rad = math.radians(direction_deg)
        dx = math.cos(rad)
        dy = math.sin(rad)

        closest_hit = None
        closest_wall = None
        min_dist = float("inf")

        for wall in self.walls:
            hit = wall.clipline((ox, oy), (ox + dx * 10000, oy + dy * 10000))
            if hit:
                (x1, y1), _ = hit
                hx, hy = x1, y1

                dist = (hx - ox) ** 2 + (hy - oy) ** 2
                if dist < min_dist:
                    min_dist = dist
                    closest_hit = (hx, hy)
                    closest_wall = wall

        if closest_hit is None:
            end = (ox + dx * 1000, oy + dy * 1000)
            self.rays.append(((ox, oy), end))
            return

        hx, hy = closest_hit
        self.rays.append(((ox, oy), (hx, hy)))

        # NEW: blue "sound awareness" ray to player
        self.blue_rays.append(((hx, hy), (self.mx, self.my)))

        nx, ny = self.get_normal(closest_wall, hx, hy)

        # incident vector
        ivx, ivy = dx, dy
        dot = ivx * nx + ivy * ny

        # reflection
        rx = ivx - 2 * dot * nx
        ry = ivy - 2 * dot * ny

        # ---- BOUNCE ENHANCEMENT MAGIC ----
        # slight "energy kick" so it feels more alive
        bounce_boost = 1.05
        rx *= bounce_boost
        ry *= bounce_boost

        # tiny chaos jitter (prevents perfect sterile angles)
        jitter = 0.03
        rx += (random.random() - 0.5) * jitter
        ry += (random.random() - 0.5) * jitter

        # re-normalize so direction stays stable
        length = math.hypot(rx, ry)
        if length != 0:
            rx /= length
            ry /= length

        eps = 0.5
        new_origin = (hx + rx * eps, hy + ry * eps)

        new_angle = math.degrees(math.atan2(ry, rx))

        self.shoot_single_ray(new_origin, new_angle, bounce + 1)

    def draw(self):
        self.screen.fill((0, 0, 0))

        for wall in self.walls:
            pygame.draw.rect(self.screen, (0, 255, 0), wall)

        for a, b in self.rays:
            pygame.draw.line(self.screen, (255, 0, 0), a, b, 1)
            
        for a, b in self.blue_rays:
            pygame.draw.line(self.screen, (0, 120, 255), a, b, 1)