"""Tracking attack - bullets follow the player."""

import math
from .base_attack import BaseAttackType


class TrackingAttack(BaseAttackType):
    """
    Tracking pattern - bullets aimed at player position.
    Creates homing/targeted fire.
    """
    
    def __init__(self, x, y, spread=45, spawn_interval=0.08, bullet_speed=100, enabled=True):
        """
        Args:
            spread: Spread angle around player (degrees)
            spawn_interval: Time between shots (seconds)
            bullet_speed: Speed of each bullet (pixels/sec)
        """
        super().__init__(x, y, enabled)
        self.spread = spread
        self.spawn_interval = spawn_interval
        self.bullet_speed = bullet_speed
        self.spawn_timer = 0.0
        self.num_bullets = 3  # Bullets per shot
        
    def _spawn(self, dt, engine, player_x, player_y):
        """Spawn tracking bullets toward player."""
        self.spawn_timer += dt
        
        if self.spawn_timer >= self.spawn_interval:
            self.spawn_timer = 0.0
            
            # Calculate angle to player
            dx = player_x - self.x
            dy = player_y - self.y
            angle_to_player = math.degrees(math.atan2(dy, dx))
            
            # Spread bullets around player direction
            for i in range(self.num_bullets):
                offset = (i - self.num_bullets / 2) * (self.spread / max(1, self.num_bullets - 1))
                angle = angle_to_player + offset
                
                engine.spawn_at_angle(
                    self.x,
                    self.y,
                    angle,
                    self.bullet_speed,
                    size=2,
                    color=(255, 200, 50)  # Gold
                )

