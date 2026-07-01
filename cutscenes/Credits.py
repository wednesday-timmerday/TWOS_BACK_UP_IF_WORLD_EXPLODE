from ui.textengine.textengine import TextEngine
import pygame

# ofc better cutscene, but this will do for now

class cutscene:
    def __init__(self, player, world, loader):
        self.dialogue_id = "Credits"
        self.player = player
        self.world = world
        self.loader = loader
        self.dt = 0
        self.txtengine = TextEngine()
        self.txtengine1 = TextEngine()
        self.txtengine.start_text(f"""Main idea: Wubwizard& &further elaborated: Joris, Tigo& &Main Artist: Carpet& &Concept art: Tigo& &Main coder: Joris& &Sound tracks: Wubwizard& &Sound effects: Wubwizard& &"Shadow rock": based off “Flowey”&from the game Undertale& & &Special thanks to:&Quinosaur&Everan&Devatlas& &And thanks to you, {player.true_name}, &for playing the game
""")
        self.txtengine1.start_text(f"& & & & & & & & & & & & & & & & & & & & & & &And thanks to you, {player.true_name}, &for playing the game¼")
        self.alpha = 0
        self.black_overlay = pygame.Surface((1280, 720), pygame.SRCALPHA)

    def start_scroll(self):
        if self.loader.text_y >= -1260:
            self.loader.text_y -= 60 * self.dt
        self.txtengine.update(self.dt)
        self.txtengine1.update(self.dt)

    def draw_front(self, loader, screen):
        screen.fill((0,0,0))
        self.txtengine.draw(x=self.loader.text_x, y=self.loader.text_y + 720, surface=screen)
        if self.loader.text_y <= -1260:
            self.black_overlay.fill((0, 0, 0, round(self.alpha % 256)))
            screen.blit(self.black_overlay, (0, 0))
            if self.alpha >= 255:
                self.alpha = 255
            else:
                self.alpha += 127*self.dt
            self.txtengine1.draw(x=self.loader.text_x, y=self.loader.text_y + 720, surface=screen)