"""Base class for all attack types."""


class BaseAttackType:
    """
    Base class for attack patterns.
    
    Subclasses implement the update() method to spawn bullets.
    """
    
    def __init__(self, x, y, enabled=True):
        """
        Args:
            x, y: Center position for attack
            enabled: Whether attack is active
        """
        self.x = x
        self.y = y
        self.enabled = enabled
        self.time = 0.0  # Elapsed time counter
        
    def update(self, dt, engine, player_x, player_y):
        """
        Called each frame to update attack.
        
        Args:
            dt: Delta time (seconds)
            engine: BulletHellEngine instance
            player_x, player_y: Player position (for tracking attacks)
        """
        if not self.enabled:
            return
        
        self.time += dt
        self._spawn(dt, engine, player_x, player_y)
        self._update(dt, engine, player_x, player_y)
    
    def _spawn(self, dt, engine, player_x, player_y):
        """Override in subclass to spawn bullets."""
        raise NotImplementedError(f"{self.__class__.__name__}._spawn() not implemented")
    
    def _update(self, dt, engine, player_x, player_y):
        """
        Override in subclass for per-frame attack updates.
        Called after _spawn() each frame. Optional - default is no-op.
        
        Use this for:
        - Modifying bullet velocities (homing)
        - Rotating attack center
        - Changing behavior based on time
        - State management
        """
        pass  # Override in subclass if needed
    
    def reset(self):
        """Reset attack state (time counter, etc)."""
        self.time = 0.0
    
    def set_position(self, x, y):
        """Update attack origin position."""
        self.x = x
        self.y = y
    
    def enable(self):
        """Activate attack."""
        self.enabled = True
    
    def disable(self):
        """Deactivate attack."""
        self.enabled = False
    
    def toggle(self):
        """Toggle attack state."""
        self.enabled = not self.enabled

