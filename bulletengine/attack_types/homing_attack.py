"""Homing attack - bullets track the player."""

import math
from .base_attack import BaseAttackType


class HomingAttack(BaseAttackType):
    """
    Homing pattern - bullets actively follow the player.
    Spawns bullets with tracking behavior.
    """
    
    def __init__(self, x, y, num_bullets=5, spawn_interval=0.3, bullet_speed=100, 
                 homing_strength=0.8, enabled=True):
        """
        Args:
            num_bullets: Bullets spawned per burst
            spawn_interval: Time between bursts (seconds)
            bullet_speed: Initial bullet speed (pixels/sec)
            homing_strength: How aggressively bullets track (0-1)
                0.0 = straight line (no tracking)
                0.5 = moderate curving
                1.0 = instant turn toward player
        """
        super().__init__(x, y, enabled)
        self.num_bullets = num_bullets
        self.spawn_interval = spawn_interval
        self.bullet_speed = bullet_speed
        self.homing_strength = homing_strength
        self.spawn_timer = 0.0
        
    def _spawn(self, dt, engine, player_x, player_y):
        """Spawn homing bullets spread around spawn point."""
        self.spawn_timer += dt
        
        if self.spawn_timer >= self.spawn_interval:
            self.spawn_timer = 0.0
            
            for i in range(self.num_bullets):
                # Spread bullets around center
                angle = (i * 360.0 / self.num_bullets)
                
                rad = math.radians(angle)
                vx = math.cos(rad) * self.bullet_speed
                vy = math.sin(rad) * self.bullet_speed
                
                # Spawn with homing toward player
                engine.spawn_homing(
                    self.x,
                    self.y,
                    vx,
                    vy,
                    target_x=player_x,
                    target_y=player_y,
                    homing_strength=self.homing_strength,
                    size=2,
                    color=(200, 100, 255)  # Purple
                )

