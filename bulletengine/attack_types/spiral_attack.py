"""Spiral attack - rotating pattern emanating from center."""

import math
from .base_attack import BaseAttackType


class SpiralAttack(BaseAttackType):
    """
    Spiral pattern - bullets emanate at rotating angles.
    Creates a spinning spiral effect.
    """
    
    def __init__(self, x, y, num_rays=20, spawn_interval=0.01, bullet_speed=140, enabled=True):
        """
        Args:
            num_rays: Number of rays in spiral
            spawn_interval: Time between spawn waves (seconds)
            bullet_speed: Speed of each bullet (pixels/sec)
        """
        super().__init__(x, y, enabled)
        self.num_rays = num_rays
        self.spawn_interval = spawn_interval
        self.bullet_speed = bullet_speed
        self.spawn_timer = 0.0
        self.angle_offset = 0.0
        self.rotation_speed = 90.0  # Degrees per second
        
    def _spawn(self, dt, engine, player_x, player_y):
        """Spawn spiral bullets."""
        self.spawn_timer += dt
        self.angle_offset += self.rotation_speed * dt
        
        if self.spawn_timer >= self.spawn_interval:
            self.spawn_timer = 0.0
            
            for i in range(self.num_rays):
                angle = self.angle_offset + (i * 360.0 / self.num_rays)
                engine.spawn_at_angle(
                    self.x,
                    self.y,
                    angle,
                    self.bullet_speed,
                    size=2,
                    color=(255, 100, 50)  # Orange
                )
    
    def _update(self, dt, engine, player_x, player_y):
        """Update spiral attack - can modify rotation speed."""
        # Optional: Accelerate rotation as time progresses
        self.rotation_speed += 5 * dt  # Spiral speeds up

