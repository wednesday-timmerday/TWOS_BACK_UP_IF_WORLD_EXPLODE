import pygame
from assetsLoader import Loader
from ui.textengine.textengine import TextEngine
from ui.textengine.textengine import TextEngine as TXT1
from BtnHandeler import btnHandeler

# TF IS TIS FUCKING CODE


#I dont want to do ts rn
# 
# TODO finish ts

class Menu:
    def __init__(self, screen, player):
        self.screen = screen
        self.player = player
        self.showing = False
        self.player_emotion_images = []
        total_emotions = 0 + 1 #+1 for the range
        for i in range(0, total_emotions):
            img = pygame.image.load(Loader("ui/menu/midgamemenuimages/emotions").load(f"emotion_{i}.png"))
            self.player_emotion_images.append({
                "Name": i,
                "Image_path": f"emotion_{i}.png",
                "image": img
            })
            print(f"X: {self.player_emotion_images}")
        self.bg_img = pygame.image.load(Loader("ui/menu/midgamemenuimages").load("bg.png"))

        self.curr_emotion = 0

        self.txt_engine = TextEngine()
        self.txt_engine1 = TXT1()
        self.text_finished_flag = False
        self.btn_down = False
        self.left_txt = (
            f"Attack: {self.player.atk}"
            f"&Defense: {self.player.defense}"
            f"&Dollars: {self.player.money}"
        )

        self.btnhandeler = btnHandeler()
    def handle_keys(self):
        """Helper function to handle inputs"""
        if self.btnhandeler.get_btn_pressed("ctrl"):
            if not self.showing and not self.btn_down and not self.player.incutscene:
                self.left_txt = (
                    f"Attack: {self.player.atk}"
                    f"&Defense: {self.player.defense}"
                    f"&Dollars: {self.player.money}"
                )
                self.showing = True
                self.player.can_move = False
                self.player.curr_animation = "Idle"
            elif self.showing and not self.btn_down:
                self.left_txt = (
                    f"Attack: {self.player.atk}"
                    f"&Defense: {self.player.defense}"
                    f"&Dollars: {self.player.money}"
                )
                self.showing = False
                self.player.can_move = True
                self.player.curr_animation = "Idle"
                
            self.btn_down = True
        else:
            self.btn_down = False

    def update(self, dt):
        self.handle_keys()
        if not self.text_finished_flag:
            self.txt_engine.start_text(f"{self.player.name}", "")
            self.txt_engine.char_index = len(self.txt_engine.text)
            self.txt_engine1.start_text(self.left_txt, "")
            self.txt_engine1.char_index = len(self.txt_engine1.text)
            self.text_finished_flag = True

        self.txt_engine.update(dt)
        self.txt_engine1.update(dt)
    def draw(self, screen, true_screen):
        self.true_screen = true_screen
        """Render the final menu"""
        if self.showing:
            screen.blit(self.bg_img, (0,0))

            for i, btn_info in enumerate(self.player_emotion_images):
                if self.curr_emotion == btn_info["Name"]:
                    screen.blit(btn_info["image"], (205,18))

            