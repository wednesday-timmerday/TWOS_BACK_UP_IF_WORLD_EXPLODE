"""QUICK START: Per-Attack Updates + Homing Bullets"""

# ============================================================
# EXAMPLE 1: SIMPLE PER-ATTACK UPDATE
# ============================================================

from bulletengine.attack_types import BaseAttackType

class AcceleratingSpiral(BaseAttackType):
    """Spiral that gets faster over time."""
    
    def __init__(self, x, y):
        super().__init__(x, y)
        self.rotation_speed = 90.0
        self.angle_offset = 0.0
        self.spawn_timer = 0.0
    
    def _spawn(self, dt, engine, px, py):
        """Spawn bullets in spiral."""
        self.spawn_timer += dt
        self.angle_offset += self.rotation_speed * dt
        
        if self.spawn_timer > 0.01:
            self.spawn_timer = 0.0
            for i in range(20):
                angle = self.angle_offset + (i * 18)
                engine.spawn_at_angle(self.x, self.y, angle, 140)
    
    def _update(self, dt, engine, px, py):
        """Update: Make spiral faster each frame."""
        self.rotation_speed += 5 * dt  # +5Â°/sec per second


# Use it
attack = AcceleratingSpiral(533, 350)
engine.add_attack(attack)


# ============================================================
# EXAMPLE 2: HOMING ATTACK (SIMPLEST VERSION)
# ============================================================

from bulletengine.bulletengine import BulletHellEngine
import math

class SimpleHoming(BaseAttackType):
    """Homing bullets toward player."""
    
    def __init__(self, x, y):
        super().__init__(x, y)
        self.spawn_timer = 0.0
    
    def _spawn(self, dt, engine, px, py):
        """Spawn homing bullets."""
        self.spawn_timer += dt
        
        if self.spawn_timer > 0.3:  # Every 0.3 seconds
            self.spawn_timer = 0.0
            
            # Spawn 5 bullets in a circle
            for i in range(5):
                angle = (i * 72)  # 360/5
                rad = math.radians(angle)
                vx = math.cos(rad) * 100
                vy = math.sin(rad) * 100
                
                # THIS IS THE KEY: spawn_homing() instead of spawn_at_angle()
                engine.spawn_homing(
                    self.x, self.y,
                    vx, vy,
                    px, py,           # â† Bullets will track this
                    homing_strength=0.7,
                    color=(255, 0, 255)  # Magenta
                )


# ============================================================
# EXAMPLE 3: HOMING WITH DYNAMIC TARGETING
# ============================================================

class SmartHoming(BaseAttackType):
    """Homing bullets that update their target each frame."""
    
    def __init__(self, x, y):
        super().__init__(x, y)
        self.spawn_timer = 0.0
        self.spawned_bullets = []  # Track our bullets
    
    def _spawn(self, dt, engine, px, py):
        """Spawn homing bullets."""
        self.spawn_timer += dt
        
        if self.spawn_timer > 0.2:
            self.spawn_timer = 0.0
            
            for i in range(6):
                angle = (i * 60)
                rad = math.radians(angle)
                vx = math.cos(rad) * 120
                vy = math.sin(rad) * 120
                
                # Spawn with current player position
                idx = engine.spawn_homing(
                    self.x, self.y,
                    vx, vy,
                    px, py,  # Current position
                    homing_strength=0.6,
                    color=(200, 50, 255)
                )
                
                if idx is not None:
                    self.spawned_bullets.append(idx)
    
    def _update(self, dt, engine, px, py):
        """Update targets to follow player NOW."""
        # Clean up dead bullets
        self.spawned_bullets = [
            idx for idx in self.spawned_bullets
            if idx < engine.max and engine.active[idx]
        ]
        
        # Update each bullet's target to player's CURRENT position
        for idx in self.spawned_bullets:
            if engine.homing_strength[idx] > 0:
                engine.target_x[idx] = px
                engine.target_y[idx] = py


# ============================================================
# EXAMPLE 4: BOSS PATTERN - DUAL ATTACKS
# ============================================================

class BossPattern(BaseAttackType):
    """Boss that alternates between homing and spiral."""
    
    def __init__(self, x, y):
        super().__init__(x, y)
        self.phase = 0
        self.phase_time = 0.0
        self.phase_duration = 4.0
    
    def _spawn(self, dt, engine, px, py):
        """Spawn different patterns based on phase."""
        
        if self.phase == 0:
            # HOMING PHASE
            if int(self.time * 4) % 1 == 0:  # Spawn 4x per second
                for i in range(3):
                    angle = (i * 120) + self.time * 90
                    rad = math.radians(angle)
                    vx = math.cos(rad) * 100
                    vy = math.sin(rad) * 100
                    
                    engine.spawn_homing(
                        self.x, self.y,
                        vx, vy,
                        px, py,
                        homing_strength=0.8,
                        color=(200, 100, 255)
                    )
        
        elif self.phase == 1:
            # SPIRAL PHASE
            if int(self.time * 10) % 1 == 0:
                angle_base = self.time * 180
                for i in range(16):
                    angle = angle_base + (i * 22.5)
                    engine.spawn_at_angle(
                        self.x, self.y,
                        angle, 150,
                        color=(255, 100, 50)
                    )
    
    def _update(self, dt, engine, px, py):
        """Switch phases every 4 seconds."""
        self.phase_time += dt
        
        if self.phase_time > self.phase_duration:
            self.phase_time = 0.0
            self.phase = (self.phase + 1) % 2


# ============================================================
# TESTING
# ============================================================

if __name__ == "__main__":
    import pygame
    
    pygame.init()
    screen = pygame.display.set_mode((1066, 700))
    clock = pygame.time.Clock()
    
    engine = BulletHellEngine(50000)
    
    # Test homing attack
    homing = SmartHoming(533, 350)
    engine.add_attack(homing)
    
    player_x = 533
    player_y = 350
    player_speed = 300
    
    while True:
        dt = clock.tick(60) / 1000
        
        # Input
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                exit()
        
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:
            player_x -= player_speed * dt
        if keys[pygame.K_RIGHT]:
            player_x += player_speed * dt
        if keys[pygame.K_UP]:
            player_y -= player_speed * dt
        if keys[pygame.K_DOWN]:
            player_y += player_speed * dt
        
        # Update
        engine.update_attacks(dt, player_x, player_y)
        engine.update(dt, player_x, player_y, 4, 0, 1066, 0, 700)
        
        # Draw
        screen.fill((0, 0, 0))
        engine.draw(screen)
        
        # Player
        pygame.draw.circle(screen, (0, 255, 0), (int(player_x), int(player_y)), 4)
        
        # Info
        font = pygame.font.SysFont("consolas", 16)
        stats = engine.get_stats()
        text = font.render(
            f"Homing Bullets: {stats['active_bullets']} | Move with arrow keys",
            True,
            (255, 255, 255)
        )
        screen.blit(text, (10, 10))
        
        pygame.display.flip()

