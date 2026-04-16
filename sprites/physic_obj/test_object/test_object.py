import pygame
import math



class PhysicObject:
    def __init__(self):
        # Create a simple colored rectangle as image
        self.width = 40
        self.height = 40
        self.image = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self.image.fill((150, 100, 50))  # brown box
        
        # Mass and physics parameters
        self.mass = 10

        # Starting position in world coordinates
        self.start_x = 300
        self.start_y = 400

        # Will be set by PhysicEngine
        self.world_x = self.start_x
        self.world_y = self.start_y
        self.angle = 0

    def get_forces(self, player):

        # Get vector to player
        dx = (player.world_x + player.rect.width / 2) - self.world_x
        dy = (player.world_y + player.rect.height / 2) - self.world_y

        dist = math.hypot(dx, dy)
        if dist == 0:
            return 0, 0

        # Normalize
        dx /= dist
        dy /= dist

        # Weak force
        strength = 0  # change this for stronger pulling / pushing

        force_x = dx * strength
        force_y = dy * strength

        return force_x, force_y
