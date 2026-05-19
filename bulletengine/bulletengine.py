"""
bulletengine.py — High-performance bullet-hell engine (Structure of Arrays).

Manages up to `max_bullets` simultaneous projectiles using flat arrays for
cache-friendly iteration.  Supports:

  - Multiple bullet types with custom sprites / procedural shapes
  - Per-bullet image rendering with optional velocity-rotation
  - Homing / tracking behaviour
  - Attack-type plug-in system (see attack_types/)

--------------------------------------------------------------------
QUICK START
--------------------------------------------------------------------

    import pygame
    from bulletengine.bulletengine import BulletHellEngine

    engine = BulletHellEngine(max_bullets=60000)

    # Spawn a single bullet
    engine.spawn_at_angle(x=400, y=300, angle=45, speed=200)

    # Spawn a laser bullet
    engine.spawn_at_angle(400, 300, 90, 300, bullet_type="laser")

    # Game loop
    engine.update(dt, px, py, pr, left=0, right=800, top=0, bottom=600)
    engine.draw(screen)

--------------------------------------------------------------------
"""

import math


class BulletHellEngine:
    """
    High-performance bullet manager using Structure of Arrays (SoA) design.

    Every property is stored as a flat Python list so that the update loop
    iterates contiguous memory rather than chasing object pointers.

    Attributes:
        max (int):          Hard cap on simultaneous bullets.
        active_count (int): Current number of live bullets.
        active_attacks:     List of registered AttackType instances.
    """

    def __init__(self, max_bullets: int = 60000, fight_loader=None):
        """
        Args:
            max_bullets: Maximum simultaneous bullets.  Tune down on weak
                         hardware; tune up for dense patterns.  Default 60 000.
        """
        self.max = max_bullets
        self.fight_loader = fight_loader

        # -- Kinematics --
        self.x   = [0.0] * self.max
        self.y   = [0.0] * self.max
        self.vx  = [0.0] * self.max
        self.vy  = [0.0] * self.max
        
        # -- Rotation --
        self.angle            = [0.0]  * self.max   # Rotation angle in degrees
        self.angular_velocity = [0.0]  * self.max   # Rotation speed in degrees/second

        # -- Shape & lifetime --
        self.size         = [2]            * self.max
        self.lifetime     = [0.0]          * self.max   # Current age (seconds)
        self.max_lifetime = [float('inf')] * self.max   # 0 / inf = unlimited
        self.active       = [False]        * self.max

        # -- Visuals --
        self.color       = [(255, 70, 70)] * self.max   # Fallback RGB
        self.bullet_type = ["dot"]         * self.max   # Type key (str)

        # -- Collision --
        self.hit_player  = [False] * self.max
        self.hit_half_w  = [0.0]  * self.max   # OBB half-width  (0 = use circle)
        self.hit_half_h  = [0.0]  * self.max   # OBB half-height (0 = use circle)

        # -- Homing --
        self.target_x        = [0.0] * self.max
        self.target_y        = [0.0] * self.max
        self.homing_strength = [0.0] * self.max   # 0 = straight, 1 = instant

        # -- Object pool --
        self.free_list  = list(range(self.max))
        self.free_count = self.max
        self.active_count = 0

        # -- Attack types --
        self.active_attacks = []

        # -- Surface cache: {(type_key, size) -> pygame.Surface} --
        self._surf_cache: dict = {}

        # -- Warning stuff --
        self.warnings = []
        self.dt = 0.0

    # ---------------------------------------------------------------
    # Spawning
    # ---------------------------------------------------------------

    def spawn(
        self,
        x: float,
        y: float,
        vx: float,
        vy: float,
        *,
        size:        int   = 2,
        lifetime:    float = float('inf'),
        color:       tuple = (255, 70, 70),
        bullet_type: str   = "dot",
        angular_velocity: float = 0.0,
    ):
        """
        Spawn a bullet using explicit velocity components.

        Args:
            x, y:        World position (pixels).
            vx, vy:      Velocity components (pixels / second).
            size:        Collision radius (pixels).
            lifetime:    Max age before auto-despawn (seconds).
                         Use ``float('inf')`` for no expiry.
            color:       RGB tuple override.  If None, uses the type default.
            bullet_type: String key from BulletTypes (e.g. ``"laser"``).
            angular_velocity: Rotation speed in degrees/second.

        Returns:
            int | None: Bullet index, or None if the pool is exhausted.
        """
        if self.free_count <= 0:
            return None

        idx = self.free_list[self.free_count - 1]
        self.free_count -= 1

        self.x[idx]            = x
        self.y[idx]            = y
        self.vx[idx]           = vx
        self.vy[idx]           = vy
        self.size[idx]         = size
        self.lifetime[idx]     = 0.0
        self.max_lifetime[idx] = lifetime
        self.active[idx]       = True
        self.color[idx]        = color
        self.bullet_type[idx]  = bullet_type
        self.hit_player[idx]   = False
        self.hit_half_w[idx]   = 0.0
        self.hit_half_h[idx]   = 0.0
        self.homing_strength[idx] = 0.0
        self.angle[idx]           = 0.0
        self.angular_velocity[idx] = angular_velocity

        self.active_count += 1
        return idx

    def spawn_at_angle(
        self,
        x: float,
        y: float,
        angle: float,
        speed: float,
        *,
        size:        int   = 2,
        lifetime:    float = float('inf'),
        color:       tuple = (255, 70, 70),
        bullet_type: str   = "dot",
        angular_velocity: float = 0.0,
    ):
        """
        Spawn a bullet using angle + speed instead of raw velocity.

        Args:
            x, y:        World position.
            angle:       Direction in degrees (0 = right, 90 = down).
            speed:       Magnitude in pixels / second.
            size:        Collision radius.
            lifetime:    Auto-despawn age (seconds).
            color:       RGB override.
            bullet_type: String key from BulletTypes.
            angular_velocity: Rotation speed in degrees/second.

        Returns:
            int | None: Bullet index, or None if pool exhausted.

        Example::

            # Fire a laser upward
            engine.spawn_at_angle(400, 300, 270, 400, bullet_type="laser")
        """
        rad = math.radians(angle)
        return self.spawn(
            x, y,
            math.cos(rad) * speed,
            math.sin(rad) * speed,
            size=size,
            lifetime=lifetime,
            color=color,
            bullet_type=bullet_type,
            angular_velocity=angular_velocity,
        )

    def spawn_homing(
        self,
        x: float,
        y: float,
        vx: float,
        vy: float,
        target_x: float,
        target_y: float,
        *,
        homing_strength: float = 0.5,
        size:            int   = 2,
        lifetime:        float = float('inf'),
        color:           tuple = (255, 70, 70),
        bullet_type:     str   = "dot",
    ):
        """
        Spawn a bullet that curves toward a target.

        The bullet starts with velocity ``(vx, vy)`` and each frame nudges
        toward ``(target_x, target_y)`` proportionally to ``homing_strength``.
        Call ``engine.target_x[idx] = new_x`` every frame to update the target.

        Args:
            x, y:             Spawn position.
            vx, vy:           Initial velocity (pixels / second).
            target_x, target_y: Position to track.
            homing_strength:  Tracking aggressiveness.
                              ``0.0`` → straight line.
                              ``0.5`` → moderate curve.
                              ``1.0`` → instant direction flip.
            size:             Collision radius.
            lifetime:         Auto-despawn age.
            color:            RGB override.
            bullet_type:      String key from BulletTypes.

        Returns:
            int | None: Bullet index, or None if pool exhausted.
        """
        idx = self.spawn(
            x, y, vx, vy,
            size=size, lifetime=lifetime, color=color, bullet_type=bullet_type,
        )
        if idx is not None:
            self.target_x[idx]        = target_x
            self.target_y[idx]        = target_y
            self.homing_strength[idx] = max(0.0, min(1.0, homing_strength))
        return idx

    # ---------------------------------------------------------------
    # Update
    # ---------------------------------------------------------------

    def update(
        self,
        dt: float,
        px: float,
        py: float,
        pr: float,
        left:   float,
        right:  float,
        top:    float,
        bottom: float,
        on_hit=None,
    ):
        """
        Advance physics, lifetime, and collision for all active bullets.

        Args:
            dt:                 Delta time in seconds.
            px, py:             Player centre position.
            pr:                 Player collision radius.
            left, right:        Horizontal arena bounds.
            top, bottom:        Vertical arena bounds.
            on_hit:             Optional callback ``fn(bullet_index)`` called
                                when a bullet hits the player.

        Notes:
            Bullets are culled 500 px outside the arena bounds, so patterns
            that spawn just off-screen have time to enter the play area.
        """
        self.dt = dt
        i = 0
        while i < self.max:
            if not self.active[i]:
                i += 1
                continue

            # --- Homing ---
            if self.homing_strength[i] > 0:
                dx   = self.target_x[i] - self.x[i]
                dy   = self.target_y[i] - self.y[i]
                dist = math.sqrt(dx * dx + dy * dy)
                if dist > 0:
                    spd     = math.sqrt(self.vx[i] ** 2 + self.vy[i] ** 2) or 1.0
                    want_vx = (dx / dist) * spd
                    want_vy = (dy / dist) * spd
                    s = self.homing_strength[i]
                    self.vx[i] += (want_vx - self.vx[i]) * s
                    self.vy[i] += (want_vy - self.vy[i]) * s

            # --- Movement ---
            self.x[i] += self.vx[i] * dt
            self.y[i] += self.vy[i] * dt
            
            # --- Rotation ---
            self.angle[i] += self.angular_velocity[i] * dt

            # --- Lifetime ---
            ml = self.max_lifetime[i]
            if ml != float('inf') and ml > 0:
                self.lifetime[i] += dt
                if self.lifetime[i] >= ml:
                    self._deactivate(i)
                    i += 1
                    continue

            # --- Bounds cull ---
            if (self.x[i] < left  - 500 or self.x[i] > right  + 500 or
                self.y[i] < top   - 500 or self.y[i] > bottom + 500):
                self._deactivate(i)
                i += 1
                continue

            # --- Player collision (OBB vs circle when rotated, else circle-circle) ---
            if not self.hit_player[i]:
                dx = self.x[i] - px
                dy = self.y[i] - py
                hw = self.hit_half_w[i]
                hh = self.hit_half_h[i]
                if hw > 0 and hh > 0:
                    # Rotate player position into bullet local space
                    ang = math.radians(-self.angle[i])
                    cos_a = math.cos(ang)
                    sin_a = math.sin(ang)
                    lx = cos_a * dx - sin_a * dy
                    ly = sin_a * dx + cos_a * dy
                    # Clamp to OBB edge, measure remaining distance to circle
                    cx2 = max(-hw, min(hw, lx))
                    cy2 = max(-hh, min(hh, ly))
                    dist_sq = (lx - cx2) ** 2 + (ly - cy2) ** 2
                    hit = dist_sq < pr * pr
                else:
                    dist_sq = dx * dx + dy * dy
                    hit = dist_sq < (self.size[i] + pr) ** 2
                if hit:
                    self.hit_player[i] = True
                    if on_hit:
                        on_hit(i)
                    self._deactivate(i)
                    i += 1
                    continue

            i += 1

    # ---------------------------------------------------------------
    # Warning
    # ---------------------------------------------------------------
    def add_warning(self, x, y, size, flash=True, time_out=0.5):
        """"
        Add warnings...
        ...---...
        """
        self.warnings.append({
                "x": x,
                "y": y,
                "size": size,
                "flash": flash,
                "timeout": time_out,
                "elapsed": 0.0
            })
    # ---------------------------------------------------------------
    # Draw
    # ---------------------------------------------------------------

    def draw(self, screen):
        """
        Render all active bullets to a pygame surface.

        Bullets with a sprite (image_path set on their BulletType) are drawn
        via ``blit``; procedural shapes use ``pygame.draw``.  Rotation is
        applied for types with ``rotate_to_velocity=True``.

        Args:
            screen: A ``pygame.Surface`` to draw onto.
        """
        import pygame
        from .bullet_types import BulletTypes

        for i in range(self.max):
            if not self.active[i]:
                continue

            btype = BulletTypes.get(self.bullet_type[i])
            sz    = self.size[i]
            cx    = int(self.x[i])
            cy    = int(self.y[i])

            # --- Try to get/make a surface ---
            cache_key = (self.bullet_type[i], sz)
            surf = self._surf_cache.get(cache_key)

            if surf is None:
                surf = btype.make_surface(sz)
                self._surf_cache[cache_key] = surf  # may be None

            if surf is not None:
                # Determine rotation angle
                angle_deg = self.angle[i]  # Use stored angle
                
                # If rotate_to_velocity is enabled and velocity exists AND angular velocity is not being used, use velocity direction
                if btype.rotate_to_velocity and self.angular_velocity[i] == 0.0 and (self.vx[i] != 0 or self.vy[i] != 0):
                    angle_deg = math.degrees(math.atan2(self.vy[i], self.vx[i]))
                
                # Apply rotation
                draw_surf = pygame.transform.rotate(surf, -angle_deg)
                # Sync OBB to pre-rotation surface dimensions
                sw, sh = surf.get_size()
                self.hit_half_w[i] = sw / 2
                self.hit_half_h[i] = sh / 2

                rect = draw_surf.get_rect(center=(cx, cy))
                screen.blit(draw_surf, rect)
            else:
                # Fallback: plain circle
                pygame.draw.circle(screen, self.color[i], (cx, cy), max(1, sz))

        if self.fight_loader.current_turn == 1:
            for warning in self.warnings:
                warning["elapsed"] += self.dt
                warning["timeout"] -= self.dt
                
                # Flicker at 5 Hz (alternates every 0.1 seconds)
                flicker_phase = int((warning["elapsed"] * 5) % 2)
                color = (255, 0, 0) if flicker_phase == 0 else (255, 100, 0)
                
                if warning["timeout"] > 0:
                    pygame.draw.rect(screen, color, (warning["x"], warning["y"], warning["size"], 360), 2)
            
            self.warnings = [w for w in self.warnings if w["timeout"] > 0]

    # ---------------------------------------------------------------
    # Pool management
    # ---------------------------------------------------------------

    def _deactivate(self, idx: int):
        """Return bullet at *idx* to the free pool (O(1))."""
        self.active[idx] = False
        self.free_list[self.free_count] = idx
        self.free_count  += 1
        self.active_count -= 1

    def clear(self):
        """Despawn all active bullets immediately."""
        for i in range(self.max):
            if self.active[i]:
                self._deactivate(i)

    # ---------------------------------------------------------------
    # Attack type system
    # ---------------------------------------------------------------

    def add_attack(self, attack_type):
        """
        Register an AttackType instance so it is updated automatically.

        Args:
            attack_type: Any subclass of BaseAttackType.
        """
        self.active_attacks.append(attack_type)

    def remove_attack(self, attack_type):
        """
        Unregister an AttackType instance.

        Args:
            attack_type: Previously added AttackType instance.
        """
        if attack_type in self.active_attacks:
            self.active_attacks.remove(attack_type)

    def update_attacks(self, dt: float, *args, **kwargs):
        """
        Call ``update(dt, engine, *args, **kwargs)`` on every registered attack.

        Args:
            dt:       Delta time in seconds.
            *args:    Forwarded to each attack's update() — typically
                      ``player_x, player_y``.
            **kwargs: Extra keyword arguments forwarded to each attack.

        Example::

            engine.update_attacks(dt, player_x, player_y)
        """
        for attack in self.active_attacks:
            attack.update(dt, self, *args, **kwargs)

    # ---------------------------------------------------------------
    # Utilities
    # ---------------------------------------------------------------

    def get_stats(self) -> dict:
        """
        Return a snapshot of engine state for debugging / HUD display.

        Returns:
            dict with keys:
                ``active_bullets``   — currently live bullet count
                ``max_bullets``      — pool capacity
                ``pool_usage``       — usage percentage (0–100)
                ``free_slots``       — available pool slots
                ``active_attacks``   — number of registered attack types
        """
        return {
            'active_bullets': self.active_count,
            'max_bullets':    self.max,
            'pool_usage':     self.active_count / self.max * 100,
            'free_slots':     self.free_count,
            'active_attacks': len(self.active_attacks),
        }

    def invalidate_surface_cache(self):
        """
        Clear cached bullet surfaces.

        Call this if you change a BulletType's properties at runtime and want
        the new visuals to take effect immediately.
        """
        self._surf_cache.clear()

    def register_btype(self, name_for_btype, img_path=None, size=4, rotate_to_vel=False, glow=False):
        """
        Register a new bullet_type

        Use this if the type of bullet isnt there
        """
        from .bullet_types import BulletTypes
        return BulletTypes.register(name_for_btype, image_path=img_path, size=size, rotate_to_velocity=rotate_to_vel, glow=glow)