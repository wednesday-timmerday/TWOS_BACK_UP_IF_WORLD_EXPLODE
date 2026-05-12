import pygame
import string
import json
import os
from assetsLoader import Loader
import ui.textengine.textengine as TextEngine
import sys


class NameScreen:

    def __init__(self, screen):

        self.screen = screen

        self.font_loader = Loader("ui/menu")
        self.toby_loader = Loader("ui")
        self.font_path = self.font_loader.load("PixelFont.ttf")
        self.font = pygame.font.Font(self.font_path, 24)

        self.text_engine = TextEngine.TextEngine()

        # phases
        self.step = -2
        self.dialog_index = 0

        self.first_time = False

        self.wait_timer = 0
        self._dialog_started = False
        self.is_teto = False

        # --------------------------------------------------
        # quit state: 0 = normal, 1 = first quit, 2 = second quit, 3+ = exit
        # --------------------------------------------------
        self.quit_state_path = self.font_loader.load("quit_state.json")
        self.quit_count = self._load_quit_count()

        if self.quit_count >= 3:
            toby_path = self.toby_loader.load("tobytank.png")
            os.remove(toby_path)
            sys.exit(0)

        # these are still used for the name-game side effects
        potato_path = self.font_loader.load("potato.txt")

        if os.path.exists(potato_path):
            self.dialog_lines = [
                "Try again.",
                "How would you call&this ^wait1000\"thing\"?"
            ]
            self.step = 0
            os.remove(potato_path)

        elif self.quit_count == 1:
            self.dialog_lines = [
                "Why did you^wait500 stop?",
                "Was it not&^wait500interesting enough?",
                "Was it ^wait1000^special^shake3BORING^endspecial?",
                "...",
                "Can you please just&finish this quiz?", #TODO: actually google or smth if this is a quiz
                "How would you call&this ^wait1000\"thing\"?"
            ]
            self.step = 0

        elif self.quit_count == 2:
            self.dialog_lines = [
                "^special^shake4WHY DO YOU KEEP QUITTING?&^endspecial",
                "^special^shake4WHY ARE YOU THE WAY YOU ARE?&^endspecial",
                "^special^shake4WHY ARE YOU REFUSING TO MAKE MY&QUIZ&^endspecial",
                "^special^shake4IF YOU QUIT ONE MORE TIME,&ILL DELETE THIS GAME^endspecial",
                "^special^shake4YOU WILL NEVER BE ABLE TO&PLAY THIS GAME AGAIN^endspecial",
                "...",
                "How would you call&this ^wait1000\"thing\"?"
            ]
            self.step = 0

        else:
            self.dialog_lines = [
                "Are you^wait1000 there?",
                "Can you^wait1000 hear me?",
                "Great",
                "Perfect",
                "Excellent",
                "Let's start",
                "How would you call&this ^wait1000\"thing\"?"
            ]

        self.alfabet = list(string.ascii_uppercase)

        self.grid_cols = 10
        self.grid_rows = 3
        self.cell_size = 70

        self.start_x = 200
        self.start_y = 305

        self.cursor_x = 0
        self.cursor_y = 0

        self.selected_letters = []
        self.max_letters = 7

        self.player_loader = Loader("sprites/Player/animation_frames/Idle")
        self.player_img_path = self.player_loader.load("Idle_1.png")
        self.player_img = pygame.image.load(self.player_img_path)
        self.player_img = pygame.transform.scale(
            self.player_img,
            (self.player_img.get_width() * 6, self.player_img.get_height() * 6)
        )

        self.button_row = self.grid_rows
        self.buttons = ["Back", "Next"]

        self.chara_name = "Gaster"
        self.creator_name = "Player"

        self.cursor_visible = True
        self.cursor_timer = 0
        self.cursor_interval = 0.45
        self.blink_times = 0

        self.black_timer = 0
        self.teto_text_engine = TextEngine.TextEngine(font="tobytank.ttf")

        print(self.font_loader.load("firstime.txt"))

    # --------------------------------------------------

    def _load_quit_count(self):
        if not os.path.exists(self.quit_state_path):
            return 0

        try:
            with open(self.quit_state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return int(data.get("quit_count", 0))
        except Exception:
            return 0

    # --------------------------------------------------

    def _save_quit_count(self, count):
        os.makedirs(os.path.dirname(self.quit_state_path), exist_ok=True)
        with open(self.quit_state_path, "w", encoding="utf-8") as f:
            json.dump({"quit_count": count}, f, indent=4)

    # --------------------------------------------------

    def _register_quit(self):
        self.quit_count += 1
        self._save_quit_count(self.quit_count)

        if self.quit_count >= 3:
            pygame.quit()
            sys.exit(0)

    # --------------------------------------------------

    def _row_width(self, row):

        start = row * self.grid_cols
        remain = len(self.alfabet) - start

        if remain <= 0:
            return 0

        return min(self.grid_cols, remain)

    # --------------------------------------------------

    def _clamp_cursor(self):

        if self.cursor_y < 0:
            self.cursor_y = 0

        if self.cursor_y > self.button_row:
            self.cursor_y = self.button_row

        if self.cursor_y == self.button_row:
            self.cursor_x = max(0, min(self.cursor_x, 1))
        else:
            width = self._row_width(self.cursor_y)
            self.cursor_x = max(0, min(self.cursor_x, width - 1))

    # --------------------------------------------------

    def draw_intro(self, dt):

        self.text_engine.update(dt)
        self.teto_text_engine.update(dt)

        if self.dialog_index < len(self.dialog_lines):

            if not self._dialog_started:
                self.text_engine.start_text(self.dialog_lines[self.dialog_index])
                self._dialog_started = True

            if self.text_engine.finished:

                self.wait_timer += dt

                if self.wait_timer >= 2.0:

                    self.dialog_index += 1
                    self.wait_timer = 0
                    self._dialog_started = False

            self.text_engine.draw(250, 70, (255, 255, 255), size=26)

            print(self.text_engine.char_index)

            if self.dialog_index == len(self.dialog_lines) - 1 and self.text_engine.char_index >= 23:
                self.screen.blit(self.player_img, (700, 215))

            return

        self.step = 1

    # --------------------------------------------------

    def draw_name_result(self, dt, name):

        self.text_engine.update(dt)
        self.teto_text_engine.update(dt)

        # start dialog once
        if not self._dialog_started:

            if name in ("POTETO", "POTATO", "TETO", "KASANE"):
                self.teto_text_engine.start_text(
                    'YOU CANT BE ME^wait750&YOULL NEVER BE ME^wait750&I CONTROL THIS GAME REMEMBER^wait750&YOU WERE NEVER IN CONTROL',
                    "potato"
                )
                path = self.font_loader.load("potato.txt")

                print(path)

                os.makedirs(os.path.dirname(path), exist_ok=True)

                with open(path, "w", encoding="utf-8") as f:
                    f.write("")
                self.is_teto = True

            elif name in ("MIKU", "HATSUNE"):
                self.teto_text_engine.start_text(
                    'WHY DID YOU EVEN CONSIDER TO BE THAT&BLUE HAIRED CREATURE^wait750&YOU SHOULD REALLY GET SOME TASTE',
                    "potato"
                )
                path = self.font_loader.load("potato.txt")

                print(path)

                os.makedirs(os.path.dirname(path), exist_ok=True)

                with open(path, "w", encoding="utf-8") as f:
                    f.write("")
                self.is_teto = True

            elif name in ("A", "AAAAAAA", "HUMAN", "PERSON"):
                self.text_engine.start_text('Not very creative,^wait500 are you?')
                self.is_teto = False


            elif name in ("TIGO", "JORIS", "QUINTEN", "CARPET", "JOSIAH", "EVERAN", "AMY"): #The developers...
                self.text_engine.start_text('.^wait250.^wait250.^wait250')
                self.is_teto = False
            else:
                self.text_engine.start_text(f'"{name}."')
                self.is_teto = False

            self._dialog_started = True

        # --- TETO PATH ---
        if self.is_teto:

            self.teto_text_engine.draw(250, 70, (255, 255, 255), size=26)

            if self.teto_text_engine.finished:
                self.wait_timer += dt

                if self.wait_timer >= 1.5:
                    sys.exit(0)

            return False

        # --- NORMAL PATH ---
        else:

            self.text_engine.draw(250, 70, (255, 255, 255), size=26)

            if self.text_engine.finished:
                self.wait_timer += dt

                if self.wait_timer >= 1.5:
                    self.wait_timer = 0
                    self._dialog_started = False
                    return True

            return False

    # --------------------------------------------------

    def draw_creator_prompt(self, dt):

        self.text_engine.update(dt)
        self.teto_text_engine.update(dt)

        if not self._dialog_started:

            self.text_engine.start_text(
                'And what about ^wait1000^special^color(255,0,0)^shake7you^endspecial?'
            )

            self._dialog_started = True

        self.text_engine.draw(250, 70, (255, 255, 255), size=26)
        self.teto_text_engine.draw(250, 70, (255, 255, 255), size=26)
        if self.text_engine.finished:
            self.wait_timer += dt

            if self.wait_timer >= 1.5:
                self.wait_timer = 0
                self._dialog_started = False
                return True

        return False

    # --------------------------------------------------

    def draw_final_dialog(self, dt):

        self.text_engine.update(dt)

        lines = [
            "Thank you for your time",
            f"you may now wake up,&^wait1000{self.chara_name}",
            "..."
        ]

        if self.dialog_index < len(lines):

            if not self._dialog_started:
                self.text_engine.start_text(lines[self.dialog_index])
                self._dialog_started = True

            if self.text_engine.finished:

                self.wait_timer += dt

                if self.wait_timer >= 1.5:
                    self.dialog_index += 1
                    self._dialog_started = False
                    self.wait_timer = 0

            self.text_engine.draw(250, 70, (255, 255, 255), size=26)

        else:
            self.save_names()
            return True

        return False

    # --------------------------------------------------

    def draw_alfabet(self):
        # draw letters
        for idx, letter in enumerate(self.alfabet):
            x = idx % self.grid_cols
            y = idx // self.grid_cols
            pos_x = self.start_x + x * self.cell_size
            pos_y = self.start_y + y * self.cell_size
            text = self.font.render(letter, False, (255, 255, 255))
            self.screen.blit(text, (pos_x, pos_y))

        # draw buttons
        for i, btn in enumerate(self.buttons):
            pos_x = self.start_x + i * self.cell_size + (200 * i)  # keep offset
            pos_y = self.start_y + self.button_row * self.cell_size
            text = self.font.render(btn, False, (255, 255, 255))
            self.screen.blit(text, (pos_x, pos_y))

        # draw typed letters
        for i, letter in enumerate(self.selected_letters):
            pos_x = 200 + i * self.cell_size
            pos_y = 150
            text = self.font.render(letter, False, (255, 255, 255))
            self.screen.blit(text, (pos_x, pos_y))

        # draw underscore placeholders
        for i in range(len(self.selected_letters), self.max_letters):
            pos_x = 200 + i * self.cell_size
            pos_y = 150
            text = self.font.render("_", False, (255, 255, 255))
            self.screen.blit(text, (pos_x, pos_y))

        # --- draw cursor ---
        if self.cursor_y == self.button_row:
            # buttons row: apply same offset as the button text
            cursor_x_pos = self.start_x + self.cursor_x * self.cell_size + (200 * self.cursor_x)
            cursor_y_pos = self.start_y + self.cursor_y * self.cell_size
        else:
            cursor_x_pos = self.start_x + self.cursor_x * self.cell_size
            cursor_y_pos = self.start_y + self.cursor_y * self.cell_size

        cursor = pygame.Rect(
            cursor_x_pos,
            cursor_y_pos,
            35,
            35
        )
        pygame.draw.rect(self.screen, (255, 0, 0), cursor, 3)

    # --------------------------------------------------

    def update_cursor(self, dt):

        self.cursor_timer += dt

        if self.cursor_timer >= self.cursor_interval:
            self.cursor_visible = not self.cursor_visible
            self.cursor_timer = 0
            self.blink_times += 1

        if self.blink_times == 6:
            self.step = 0

    def draw_flicker_cursor(self):

        if not self.cursor_visible:
            return

        cursor_rect = pygame.Rect(
            self.screen.get_width() // 2 - 5,
            self.screen.get_height() // 2 - 5,
            5,
            15
        )

        pygame.draw.rect(self.screen, (255, 255, 255), cursor_rect)

    # --------------------------------------------------

    def save_names(self):

        data = {
            "character_name": self.chara_name,
            "creator_name": self.creator_name
        }

        path = self.font_loader.load("names.json")

        print(path)

        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    # --------------------------------------------------

    def draw(self, dt):

        clock = pygame.time.Clock()

        path = self.font_loader.load("names.json")

        print(path)

        while True:

            if os.path.exists(path):

                with open(path, "r") as f:
                    data = json.load(f)
                    print(data)

                self.chara_name = data["character_name"]
                self.creator_name = data["creator_name"]

                return

            dt = clock.tick(60) / 1000
            self.screen.fill((0, 0, 0))

            for event in pygame.event.get():

                if event.type == pygame.QUIT:
                    self._register_quit()
                    pygame.quit()
                    sys.exit(0)
                    return

                if event.type == pygame.KEYDOWN and self.step in (1, 3):

                    if event.key == pygame.K_LEFT:
                        self.cursor_x -= 1

                    if event.key == pygame.K_RIGHT:
                        self.cursor_x += 1

                    if event.key == pygame.K_UP:
                        self.cursor_y -= 1

                    if event.key == pygame.K_DOWN:
                        self.cursor_y += 1

                    if event.key == pygame.K_z:

                        if self.cursor_y == self.button_row:

                            if self.cursor_x == 0:
                                if self.selected_letters:
                                    self.selected_letters.pop()

                            else:

                                if self.selected_letters:

                                    if self.step == 1:
                                        self.chara_name = "".join(self.selected_letters)
                                        self.selected_letters = []
                                        self.step = 2

                                    else:
                                        self.creator_name = "".join(self.selected_letters)
                                        self.dialog_index = 0
                                        self.step = 4

                        else:

                            idx = self.cursor_y * self.grid_cols + self.cursor_x

                            if idx < len(self.alfabet):

                                if len(self.selected_letters) < self.max_letters:
                                    self.selected_letters.append(self.alfabet[idx])

                    self._clamp_cursor()

            if self.step == -2:
                self.black_timer += dt
                if self.black_timer >= 2.0:
                    self.step = -1

            if self.step == -1:
                self.update_cursor(dt)
                self.draw_flicker_cursor()

            if self.step == 0:
                self.draw_intro(dt)

            elif self.step == 1:
                self.draw_alfabet()

            elif self.step == 2:

                if self.draw_name_result(dt, self.chara_name):
                    self.step = 2.5

            elif self.step == 2.5:

                if self.draw_creator_prompt(dt):
                    self.step = 3

            elif self.step == 3:
                self.draw_alfabet()

            elif self.step == 4:

                if self.draw_name_result(dt, self.creator_name):
                    self.dialog_index = 0
                    self.step = 5

            elif self.step == 5:

                if self.draw_final_dialog(dt):
                    return

            pygame.display.flip()
