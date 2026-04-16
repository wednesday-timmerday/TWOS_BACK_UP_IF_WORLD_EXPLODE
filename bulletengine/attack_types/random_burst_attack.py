"""Random burst attack - chaotic unpredictable fire."""

import random
from .base_attack import BaseAttackType


class RandomBurstAttack(BaseAttackType):
    """
    Random burst pattern - bullets spawn from random positions
    in random directions. Unpredictable and chaotic.
    """
    
    def __init__(self, x, y, spawn_radius=200, burst_size=100, spawn_interval=0.3, 
                 min_speed=60, max_speed=160, enabled=True):
        """
        Args:
            spawn_radius: Radius around center to spawn from
            burst_size: Bullets spawned per burst
            spawn_interval: Time between bursts (seconds)
            min_speed, max_speed: Speed range (pixels/sec)
        """
        super().__init__(x, y, enabled)
        self.spawn_radius = spawn_radius
        self.burst_size = burst_size
        self.spawn_interval = spawn_interval
        self.min_speed = min_speed
        self.max_speed = max_speed
        self.spawn_timer = 0.0
        
    def _spawn(self, dt, engine, player_x, player_y):
        """Spawn random burst."""
        self.spawn_timer += dt
        
        if self.spawn_timer >= self.spawn_interval:
            self.spawn_timer = 0.0
            
            for _ in range(self.burst_size):
                # Random position in radius
                angle = random.uniform(0, 360)
                dist = random.uniform(0, self.spawn_radius)
                
                rad = __import__('math').radians(angle)
                spawn_x = self.x + __import__('math').cos(rad) * dist
                spawn_y = self.y + __import__('math').sin(rad) * dist
                
                # Random direction and speed
                bullet_angle = random.uniform(0, 360)
                bullet_speed = random.uniform(self.min_speed, self.max_speed)
                
                engine.spawn_at_angle(
                    spawn_x,
                    spawn_y,
                    bullet_angle,
                    bullet_speed,
                    size=2,
                    color=(255, 50, 150)  # Magenta
                )
