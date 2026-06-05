import pygame
import math

"""
INFO DUMP TIME FOR FUTURE ME:

1. The wall heights will be determined by a black and white image, where pure white = 0 and pure black = X (where X will be set in level_spec, just like type flag ("is_topdown": True/False))
2. We need to find a way to accuratly "muffle" the audio (if no direct rays to player, use these as audio)
3. We need to add echo (rebounce the rays with a 5-10% chance of despawning)
4. We need to add wall bounces (path like flips dir (- = +))
5. We need to find the AVG of all that reach the player, use the first bounce and use that as audio dir

"""

class AudioTracer:
    def __init__(self, screen):
        self.rays = []
        self.step_size = 7
        self.screen = screen

    def shoot_single_ray(self, origin_x, origin_y, dir):
        #hard coded x and y's
        # TODO: make the calculate accurate
        # offset point by 100px and do some wizard stuff i found on the internet
        # 
        dir = math.radians(dir)
        dx = math.cos(dir)
        dy = math.sin(dir)
        
        x = origin_x
        y = origin_y

        #Takes a long time!
        # Vraag Hidde ofz voor optimizations
        
        while True:
            x += dx * self.step_size
            y += dy * self.step_size
        
            if x <= 0 or x >= self.screen.get_size()[0]:
                break
            if y <= 0 or y >= self.screen.get_size()[1]:
                break

        self.rays.append({"or_x": origin_x, "or_y": origin_y, "dir": dir, "final_x": x, "final_y": y})

    def draw(self):
        self.screen.fill((0,0,0))
        for i, ray in enumerate(self.rays):
            pygame.draw.line(self.screen, (255,0,0), (ray["or_x"], ray["or_y"]), (ray["final_x"], ray["final_y"]))