"""Ring attack - dense concentric circles."""

from .base_attack import BaseAttackType


class RingAttack(BaseAttackType):
    """
    Ring pattern - spawns dense concentric rings.
    Creates expanding circles that are hard to dodge.
    """
    
    def __init__(self, x, y, bullets_per_ring=60, spawn_interval=0.15, bullet_speed=120, enabled=True):
        """
        Args:
            bullets_per_ring: Number of bullets per ring
            spawn_interval: Time between rings (seconds)
            bullet_speed: Speed of each bullet (pixels/sec)
        """
        super().__init__(x, y, enabled)
        self.bullets_per_ring = bullets_per_ring
        self.spawn_interval = spawn_interval
        self.bullet_speed = bullet_speed
        self.spawn_timer = 0.0
        
    def _spawn(self, dt, engine, player_x, player_y):
        """Spawn ring pattern."""
        self.spawn_timer += dt
        
        if self.spawn_timer >= self.spawn_interval:
            self.spawn_timer = 0.0
            
            # Ring expands outward
            for i in range(self.bullets_per_ring):
                angle = (i * 360.0 / self.bullets_per_ring)
                engine.spawn_at_angle(
                    self.x,
                    self.y,
                    angle,
                    self.bullet_speed,
                    size=2,
                    color=(100, 200, 255)  # Cyan
                )

