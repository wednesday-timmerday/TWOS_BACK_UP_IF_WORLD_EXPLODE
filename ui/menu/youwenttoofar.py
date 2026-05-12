import pygame
from ui.textengine.textengine import TextEngine

class Toofar:
    def __init__(self, screen, player):
        self.screen = screen
        self.player = player
        self.text_engine = TextEngine()
        self.running = True
        self.text_engine.start_text("It seems like you have reached^wait500 an end", "potato")

    def draw(self):
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
            
            self.screen.fill((0, 0, 0))
            self.text_engine.draw(150, 180, (255,255,255), surface=self.screen)
            self.text_engine.update(self.player.dt)
            pygame.display.flip()
