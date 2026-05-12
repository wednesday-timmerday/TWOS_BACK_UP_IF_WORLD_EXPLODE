import pygame
from assetsLoader import Loader

class UsernameMenu:
    def __init__(self):
        # Load font
        font_loader = Loader("ui/menu")
        font_path = font_loader.load("PixelFont.ttf")
        try:
            self.font = pygame.font.Font(font_path, 30)
        except:
            self.font = pygame.font.SysFont("Arial", 30)
        
        self.username = ""
        self.active = True
        self.max_chars = 15

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN and len(self.username) > 0:
                # Return username when Enter is pressed and username is not empty
                return self.username
            elif event.key == pygame.K_BACKSPACE:
                # Remove last character on backspace
                self.username = self.username[:-1]
            elif len(self.username) < self.max_chars and event.unicode.isalnum():
                # Add character if it's alphanumeric and within length limit
                self.username += event.unicode
        return None

    def draw(self, screen):
        screen.fill((0, 0, 127))
        
        # Draw title
        title = self.font.render("Enter Username:", True, (255, 255, 255))
        title_rect = title.get_rect(centerx=screen.get_width()//2, y=screen.get_height()//3)
        screen.blit(title, title_rect)
        
        # Draw username box
        box_width = 400
        box_height = 50
        box_x = (screen.get_width() - box_width) // 2
        box_y = screen.get_height() // 2 - box_height // 2
        
        # Draw box background
        pygame.draw.rect(screen, (0, 0, 0), (box_x, box_y, box_width, box_height))
        pygame.draw.rect(screen, (255, 255, 255), (box_x, box_y, box_width, box_height), 2)
        
        # Draw username text
        if self.username:
            text = self.font.render(self.username, True, (255, 255, 255))
        else:
            text = self.font.render("Type your username", True, (128, 128, 128))
        text_rect = text.get_rect(center=(screen.get_width()//2, screen.get_height()//2))
        screen.blit(text, text_rect)
        
        # Draw hint
        hint = self.font.render("Press Enter to continue", True, (200, 200, 200))
        hint_rect = hint.get_rect(centerx=screen.get_width()//2, bottom=screen.get_height()-50)
        screen.blit(hint, hint_rect)
        
        pygame.display.flip()
