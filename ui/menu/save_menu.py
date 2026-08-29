import pygame
from assetsLoader import Loader

class SaveMenu:
    def __init__(self):
        #self.font = pygame.font.SysFont("Arial", 24)
        self.visible = False
        self.selected_option = 0
        self.options = ["Save", "Return"]
        self.font_loader = Loader("ui/menu")
        self.font_path = self.font_loader.load("PixelFont.ttf")
        self.font = pygame.font.Font(self.font_path, 24)
        
    def show(self):
        self.visible = True
        self.selected_option = 0
        
    def hide(self):
        self.visible = False
        
    def handle_input(self, keys):
        if not self.visible:
        
            return None
            
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            self.selected_option = 0
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            self.selected_option = 1
            
        if keys[pygame.K_z]:  # Select option
            choice = self.options[self.selected_option]
            self.hide()
            return choice
            
        if keys[pygame.K_x]:  # Cancel
            self.hide()
            return "Return"
            
        return None
        
    def draw(self, surface):
        if not self.visible:
            return
            
        # Draw menu background
        menu_width = 200
        menu_height = 100
        x = (surface.get_width() - menu_width) // 2
        y = (surface.get_height() - menu_height) // 2
        
        pygame.draw.rect(surface, (0, 0, 0), (x, y, menu_width, menu_height))
        pygame.draw.rect(surface, (255, 255, 255), (x, y, menu_width, menu_height), 2)
        
        # Draw options
        for i, option in enumerate(self.options):
            color = (255, 255, 0) if i == self.selected_option else (255, 255, 255)
            text = self.font.render(option, True, color)
            text_x = x + (menu_width - text.get_width()) // 2
            text_y = y + 20 + i * 30
            surface.blit(text, (text_x, text_y))
