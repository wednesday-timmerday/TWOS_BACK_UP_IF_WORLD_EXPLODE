import pygame
import sys

class cutscene:
    def __init__(self, player, world, loader):
        self.dialogue_id = "death"
        self.player = player
        self.world = world
        self.loader = loader
        self.dt = 0
    
    def draw_front(self, loader, surface):
        pygame.draw.rect(surface, (0, 0, 0), (0, 0, surface.get_width(), surface.get_height()))

    def respawn(self):
        self.player.lives = 6
        self.player.dead = False
        self.player.dead_timer = 0.0
        self.player.can_move = True
        self.player.apply_spawn_point(self.world.current_level)
        self.player._reset_after_respawn()
        self.player.active_cutscene = None
        return "YES"
    
    def kill_game(self):
        sys.exit(0)
