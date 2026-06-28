import pygame
from assetsLoader import Loader

class btnHandeler:
    def __init__(self):
        self.btn_file_path = Loader("ui/menu").load("btn_config.txt")
        self.key_map = {}

        with open(self.btn_file_path, "r") as f:
            for line in f:
                line = line.strip()

                if "=" not in line:
                    continue

                name, key = line.split("=", 1)

                # Convert to pygame key constant
                if key == "ctrl":
                    self.key_map[name] = pygame.K_LCTRL
                elif key == "shift":
                    self.key_map[name] = pygame.K_LSHIFT
                elif key == "up":
                    self.key_map[name] = pygame.K_UP
                elif key == "down":
                    self.key_map[name] = pygame.K_DOWN
                elif key == "left":
                    self.key_map[name] = pygame.K_LEFT
                elif key == "right":
                    self.key_map[name] = pygame.K_RIGHT
                elif key == "esc":
                    self.key_map[name] = pygame.K_ESCAPE
                else:
                    self.key_map[name] = pygame.key.key_code(key)

    def get_btn_pressed(self, btn):
        keys = pygame.key.get_pressed()

        if btn not in self.key_map:
            return False

        return keys[self.key_map[btn]]

    def get_all_btn_pressed(self):
        keys = pygame.key.get_pressed()
    
        pressed = {}
    
        for name, keycode in self.key_map.items():
            pressed[name] = keys[keycode]
    
        return pressed