import math


class BulletHellEngine:
    """High-performance bullet manager using Structure of Arrays design."""
    
    def __init__(self, max_bullets=60000):
        self.max = max_bullets
        
        # Position & velocity
        self.x = [0.0] * self.max
        self.y = [0.0] * self.max
        self.vx = [0.0] * self.max
        self.vy = [0.0] * self.max
        
        # Properties
        self.size = [2] * self.max
        self.lifetime = [0.0] * self.max      # Current age
        self.max_lifetime = [float('inf')] * self.max  # 0 = infinite
        self.active = [False] * self.max
        
        # Behavior
        self.color = [(255, 70, 70)] * self.max  # RGB tuples
        self.hit_player = [False] * self.max     # Did this bullet hit player?
        
        # Homing/tracking
        self.target_x = [0.0] * self.max         # Target position
        self.target_y = [0.0] * self.max
        self.homing_strength = [0.0] * self.max  # 0 = no homing, 1 = instant track
        
        # Object pool tracking
        self.free_list = list(range(self.max))   # Stack of free indices
        self.free_count = self.max
        self.active_count = 0
        
        # Attack type instances
        self.active_attacks = []  # List of active AttackType instances

    def spawn(self, x, y, vx, vy, size=2, lifetime=float('inf'), color=(255, 70, 70)):
        """
        Spawn bullet with velocity (not angle/speed).
        
        Args:
            x, y: World position
            vx, vy: Velocity components (pixels/sec)
            size: Collision radius
            lifetime: Max age in seconds (0 = infinite)
            color: RGB tuple
        """
        if self.free_count <= 0:
            return None  # Pool exhausted
        
        # Pop from free list (O(1))
        idx = self.free_list[self.free_count - 1]
        self.free_count -= 1
        
        self.x[idx] = x
        self.y[idx] = y
        self.vx[idx] = vx
        self.vy[idx] = vy
        self.size[idx] = size
        self.lifetime[idx] = 0.0
        self.max_lifetime[idx] = lifetime
        self.active[idx] = True
        self.color[idx] = color
        self.hit_player[idx] = False
        self.homing_strength[idx] = 0.0  # No homing by default
        
        self.active_count += 1
        return idx

    def spawn_homing(self, x, y, vx, vy, target_x, target_y, homing_strength=0.5, 
                     size=2, lifetime=float('inf'), color=(255, 70, 70)):
        """
        Spawn bullet that homes toward a target.
        
        Args:
            x, y: World position
            vx, vy: Initial velocity components
            target_x, target_y: Target position to track
            homing_strength: How aggressively to track (0-1)
                0.0 = straight line
                0.5 = moderate homing
                1.0 = instant aim at target
            size: Collision radius
            lifetime: Max age in seconds
            color: RGB tuple
        """
        idx = self.spawn(x, y, vx, vy, size, lifetime, color)
        if idx is not None:
            self.target_x[idx] = target_x
            self.target_y[idx] = target_y
            self.homing_strength[idx] = max(0.0, min(1.0, homing_strength))
        return idx

    def spawn_at_angle(self, x, y, angle, speed, size=2, lifetime=float('inf'), color=(255, 70, 70)):
        """
        Spawn bullet at angle/speed (convenience wrapper).
        
        Args:
            angle: Degrees (0-360)
            speed: Pixels per second
        """
        rad = math.radians(angle)
        vx = math.cos(rad) * speed
        vy = math.sin(rad) * speed
        return self.spawn(x, y, vx, vy, size, lifetime, color)

    def update(self, dt, px, py, pr, left, right, top, bottom, on_hit=None):
        """
        Update physics & collision for all active bullets.
        
        Args:
            dt: Delta time (seconds)
            px, py: Player center position
            pr: Player collision radius
            left, right, top, bottom: Arena bounds
            on_hit: Callback(bullet_index) when player hit
        """
        i = 0
        while i < self.max:
            if not self.active[i]:
                i += 1
                continue

            # HOMING - adjust velocity toward target
            if self.homing_strength[i] > 0:
                dx = self.target_x[i] - self.x[i]
                dy = self.target_y[i] - self.y[i]
                dist = math.sqrt(dx * dx + dy * dy)
                
                if dist > 0:
                    # Normalize direction to target
                    target_vx = (dx / dist) * (math.sqrt(self.vx[i] ** 2 + self.vy[i] ** 2) or 1)
                    target_vy = (dy / dist) * (math.sqrt(self.vx[i] ** 2 + self.vy[i] ** 2) or 1)
                    
                    # Interpolate toward target velocity
                    self.vx[i] += (target_vx - self.vx[i]) * self.homing_strength[i]
                    self.vy[i] += (target_vy - self.vy[i]) * self.homing_strength[i]

            # MOVEMENT
            self.x[i] += self.vx[i] * dt
            self.y[i] += self.vy[i] * dt

            # LIFETIME
            if self.max_lifetime[i] > 0:
                self.lifetime[i] += dt
                if self.lifetime[i] >= self.max_lifetime[i]:
                    self._deactivate(i)
                    i += 1
                    continue

            # BOUNDS
            if (self.x[i] < left - 500 or self.x[i] > right + 500 or
                self.y[i] < top - 500 or self.y[i] > bottom + 500):
                self._deactivate(i)
                i += 1
                continue

            # COLLISION (circle-to-circle)
            if not self.hit_player[i]:
                dx = self.x[i] - px
                dy = self.y[i] - py
                dist_sq = dx * dx + dy * dy
                collision_dist_sq = (self.size[i] + pr) ** 2
                
                if dist_sq < collision_dist_sq:
                    self.hit_player[i] = True
                    if on_hit:
                        on_hit(i)
                    self._deactivate(i)
                    i += 1
                    continue

            i += 1

    def _deactivate(self, idx):
        """Move bullet to inactive pool."""
        self.active[idx] = False
        self.free_list[self.free_count] = idx
        self.free_count += 1
        self.active_count -= 1

    def draw(self, screen):
        """Render all active bullets."""
        import pygame
        for i in range(self.max):
            if not self.active[i]:
                continue
            pygame.draw.circle(
                screen,
                self.color[i],
                (int(self.x[i]), int(self.y[i])),
                self.size[i]
            )

    def add_attack(self, attack_type):
        """Register an attack type instance."""
        self.active_attacks.append(attack_type)

    def remove_attack(self, attack_type):
        """Unregister an attack type instance."""
        if attack_type in self.active_attacks:
            self.active_attacks.remove(attack_type)

    def update_attacks(self, dt, *args, **kwargs):
        """Update all active attack types."""
        for attack in self.active_attacks:
            attack.update(dt, self, *args, **kwargs)

    def clear(self):
        """Deactivate all bullets."""
        for i in range(self.max):
            if self.active[i]:
                self._deactivate(i)

    def get_stats(self):
        """Return engine statistics."""
        return {
            'active_bullets': self.active_count,
            'max_bullets': self.max,
            'pool_usage': self.active_count / self.max * 100,
            'free_slots': self.free_count,
            'active_attacks': len(self.active_attacks)
        }

