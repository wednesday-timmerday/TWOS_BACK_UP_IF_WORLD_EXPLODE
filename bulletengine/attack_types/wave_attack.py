"""Wave attack - sweeping beam pattern."""

import math
from .base_attack import BaseAttackType


class WaveAttack(BaseAttackType):
    """
    Wave pattern - sweeps across arena like a radar beam.
    Creates a rotating beam with gaps for dodging.
    """
    
    def __init__(self, x, y, beam_width=30, sweep_speed=180, spawn_rate=80, bullet_speed=130, enabled=True):
        """
        Args:
            beam_width: Width of beam sweep (degrees)
            sweep_speed: How fast beam rotates (degrees/sec)
            spawn_rate: Bullets per second (density) - REDUCED for gaps
            bullet_speed: Speed of each bullet (pixels/sec)
        """
        super().__init__(x, y, enabled)
        self.beam_width = beam_width
        self.sweep_speed = sweep_speed
        self.spawn_rate = spawn_rate
        self.bullet_speed = bullet_speed
        self.spawn_timer = 0.0
        
    def _spawn(self, dt, engine, player_x, player_y):
        """Spawn sweeping wave pattern with gaps."""
        self.spawn_timer += dt
        
        # Base sweep angle
        sweep_angle = (self.time * self.sweep_speed) % 360
        
        # Only spawn bullets in bursts (creates gaps instead of continuous wall)
        spawn_every = 0.15  # Spawn burst every 0.15 seconds
        
        if self.spawn_timer >= spawn_every:
            self.spawn_timer -= spawn_every
            
            # Spawn bullets in one burst across the beam
            bullets_per_burst = int(self.spawn_rate * spawn_every)
            for _ in range(bullets_per_burst):
                # Random angle within beam
                angle_offset = __import__('random').uniform(-self.beam_width / 2, self.beam_width / 2)
                angle = sweep_angle + angle_offset
                
                engine.spawn_at_angle(
                    self.x,
                    self.y,
                    angle,
                    self.bullet_speed,
                    size=2,
                    color=(50, 255, 100)  # Green
                )
