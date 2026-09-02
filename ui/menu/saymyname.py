print("Baumkuchen")
import pygame
import string
import json
import os
from assetsLoader import Loader
import ui.textengine.textengine as TextEngine
import sys
import math
import atexit
# import cv2
import numpy as np
import pytweening
print("Baumkuchen2")



class NameScreen:

    def __init__(self, screen):
        self.screen = screen

        self.font_loader = Loader("ui/menu")
        self.file_loader = Loader(f"{os.path.expanduser('~')}/TWOSFILES/")
        self.toby_loader = Loader("ui")
        print("go")

        self.font_path = self.font_loader.load("PixelFont.ttf")
        self.font = pygame.font.Font(self.font_path, 24)

        self.text_engine = TextEngine.TextEngine()
        self.teto_text_engine = TextEngine.TextEngine(font="tobytank.ttf")
        print("ready?")

        self.step = -2
        self.dialog_index = 0
        self.first_time = False

        self.wait_timer = 0
        self._dialog_started = False
        self.is_teto = False

        self.quit_state_path = self.font_loader.load("quit_state.json")
        self.quit_count = self._load_quit_count()

        if self.quit_count >= 3:
            toby_path = self.toby_loader.load("tobytank.png")
            os.remove(toby_path)
            sys.exit(0)

        self.dialog_lines = self._build_intro_lines()

        self.alfabet = list(string.ascii_uppercase)

        self.grid_cols = 10
        self.grid_rows = 3
        self.cell_size = 70

        self.start_x = 400
        self.start_y = 400

        self.timer_y = 0
        self.bob_speed = 2.5  # radians/sec — higher = faster bob
        self.max_y_height = 30

        self.cursor_x = 0
        self.cursor_y = 0

        self.selected_letters = []
        self.max_letters = 7

        self.player_loader = Loader("sprites/Player/animation_frames/Idle")
        self.player_img_path = self.player_loader.load("Idle_1.png")
        self.hand_point_img = pygame.image.load(Loader("ui/menu/").load("point.png"))
        self.player_img = pygame.image.load(self.player_img_path)
        self.player_img = pygame.transform.scale(
            self.player_img,
            (self.player_img.get_width() * 6, self.player_img.get_height() * 6)
        )

        # # self.webcam = cv2.VideoCapture(0)
        # atexit.register(self.webcam.release)

        # native_w = self.webcam.get(cv2.CAP_PROP_FRAME_WIDTH) or 640
        # native_h = self.webcam.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480
        # target_h = self.player_img.get_height()
        # target_w = round(native_w * (target_h / native_h))
        # self.webcam_size = (target_w, target_h)  # preserves the webcam's aspect ratio

        self.button_row = self.grid_rows
        self.buttons = ["Back", "Next"]

        self.chara_name = "Gaster"
        self.creator_name = "Player"

        self.cursor_visible = True
        self.cursor_timer = 0
        self.cursor_interval = 0.45
        self.blink_times = 0

        self.black_timer = 0

        print(self.font_loader.load("firstime.txt"))

    # --------------------------------------------------
    # setup helpers
    # --------------------------------------------------

    def _build_intro_lines(self):
        potato_path = self.font_loader.load("potato.txt")

        if os.path.exists(potato_path):
            os.remove(potato_path)
            self.step = 0
            return [
                "Try again.",
                "How would you call&this ^wait1000\"thing\"?"
            ]

        if self.quit_count == 1:
            self.step = 0
            return [
                "Why did you^wait500 stop?",
                "Was it not&^wait500interesting enough?",
                "Was it ^wait1000^special^shake3BORING^endspecial?",
                "...",
                "Can you please just&finish this quiz?",
                "How would you call&this ^wait1000\"thing\"?"
            ]

        if self.quit_count == 2:
            self.step = 0
            return [
                "^special^shake4WHY DO YOU KEEP QUITTING?&^endspecial",
                "^special^shake4WHY ARE YOU THE WAY YOU ARE?&^endspecial",
                "^special^shake4WHY ARE YOU REFUSING TO MAKE MY&QUIZ&^endspecial",
                "^special^shake4IF YOU QUIT ONE MORE TIME,&ILL DELETE THIS GAME^endspecial",
                "^special^shake4YOU WILL NEVER BE ABLE TO&PLAY THIS GAME AGAIN^endspecial",
                "...",
                "How would you call&this ^wait1000\"thing\"?"
            ]

        return [
            "Did it^wait1000 work?",
            'Do you^wait1000 hear me?',
            "Doesn't matter.",
            "Let's start^wait1000 the test",
            "How would you call&this ^wait1000\"thing\"?"
        ]
        # return [
        #     "Are you^wait1000 there?",
        #     "Can you^wait1000 hear me?",
        #     "Great",
        #     "Perfect",
        #     "Excellent",
        #     "Let's start",
        #     "How would you call&this ^wait1000\"thing\"?"
        # ]

    # --------------------------------------------------
    # quit-count persistence
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

    def _save_quit_count(self, count):
        os.makedirs(os.path.dirname(self.quit_state_path), exist_ok=True)
        with open(self.quit_state_path, "w", encoding="utf-8") as f:
            json.dump({"quit_count": count}, f, indent=4)

    def _register_quit(self):
        self.quit_count += 1
        self._save_quit_count(self.quit_count)

        if self.quit_count >= 3:
            pygame.quit()
            sys.exit(0)

    # --------------------------------------------------
    # grid / cursor helpers
    # --------------------------------------------------

    def _row_width(self, row):
        start = row * self.grid_cols
        remain = len(self.alfabet) - start
        return max(0, min(self.grid_cols, remain))

    def _clamp_cursor(self):
        self.cursor_y = max(0, min(self.cursor_y, self.button_row))

        if self.cursor_y == self.button_row:
            self.cursor_x = max(0, min(self.cursor_x, 1))
        else:
            width = self._row_width(self.cursor_y)
            self.cursor_x = max(0, min(self.cursor_x, width - 1))

    def _cell_pos(self, col, row):
        return self.start_x + col * self.cell_size, self.start_y + row * self.cell_size

    def _draw_text(self, text, pos, color=(255, 255, 255)):
        self.screen.blit(self.font.render(text, False, color), pos)


    # --------------------------------------------------
    # dialog helper: runs a text-engine line and reports "finished + waited"
    # --------------------------------------------------

    def _advance_after_wait(self, dt, wait_seconds=1.5):
        self.wait_timer += dt
        if self.wait_timer >= wait_seconds:
            self.wait_timer = 0
            self._dialog_started = False
            return True
        return False

    def _start_teto(self, text):
        self.teto_text_engine.start_text(text, "potato")
        path = self.font_loader.load("potato.txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(""""[Verse 1]
            (Yu) Dokutaa kidori desu
            Ai, bakuhattero
            Kantan ni nareba
            Umatta, mataa, mataa
            Dokutaa kidori desu
            Aisou ii kamo
            Mourou, ooto mo
            Umeta, meta, meta (Yu)
            
            [Pre-Chorus]
            Doko ni mo nai kara neteitara
            Kowarete naiteru yume wo mita nda yo
            Jiki ni wa
            Uso ni miete kuruu (Yu)
            
            [Chrous]
            Kao ga donki ni nacchau yo
            Nise ga kenri wo totta nda (Yu)
            Nakunatte hoshii bonnou ga
            Douyara ikinobite shimatta
            Ikinobite shimatta nda
            Ashi ga tagame ni nacchau yo
            Uso ga douki ni natta nda (Yu)
            Utagutte hoshii honnou wo
            Douyara honshin da to omotta
            Honshin da to omotta nda, kuchoo

            [Verse 2]
            (Yu) Dokutaa kidori desu
            Zenbu yamero yo
            Atichuudo ga kandou mono ni todoku moudoku
            Sontoku no toku no hou dake
            Mawatta, watta, watta
            
            [Chorus]
            Kao ga donki ni nacchau yo (Drop it)
            Nise ga kenri wo totta nda (Yu)
            Nakunatte hoshii bonnou ga
            Douyara ikinobite shimatta
            Ikinobite shimatta nda
            Oto ga kinou ni natte shimau
            Hito ga itsuwari ni atsumaru (Yu)
            Fusagatte shimae yo mimi
            Douyara todoite inai mitai
            Todoite inai mitai ne, kuchoo
            """)
        self.is_teto = True

    # --------------------------------------------------
    # dialog screens
    # --------------------------------------------------

    def draw_intro(self, dt):
        self.text_engine.update(dt)
        self.teto_text_engine.update(dt)

        if self.dialog_index >= len(self.dialog_lines):
            self.step = 1
            return

        if not self._dialog_started:
            self.text_engine.start_text(self.dialog_lines[self.dialog_index])
            self._dialog_started = True

        if self.text_engine.finished and self._advance_after_wait(dt, 2.0):
            self.dialog_index += 1
            self._dialog_started = True  # keep started=False path below fixes this
            self._dialog_started = False

        self.text_engine.draw(125, 70, (255, 255, 255), size=26)

        is_last_line = self.dialog_index == len(self.dialog_lines) - 1
        if is_last_line and self.text_engine.char_index >= 25:
            self.timer_y += dt
            bob = (math.sin(self.timer_y * self.bob_speed) * 0.5 + 0.5) * self.max_y_height
            self.screen.blit(self.player_img, (150, 415 + bob))

    def draw_name_result(self, dt, name):
        self.text_engine.update(dt)
        self.teto_text_engine.update(dt)

        if not self._dialog_started:
            self.is_teto = False

            if name in ("POTETO", "POTATO", "TETO", "KASANE"):
                self._start_teto(
                    'YOU CANT BE ME^wait750&YOULL NEVER BE ME^wait750&'
                    'I CONTROL THIS GAME REMEMBER^wait750&YOU WERE NEVER IN CONTROL'
                )
            elif name in ("MIKU", "HATSUNE"):
                self._start_teto(
                    'WHY DID YOU EVEN CONSIDER TO BE THAT&BLUE HAIRED CREATURE^wait750&'
                    'YOU SHOULD REALLY GET SOME TASTE'
                )
            elif len(name) == 1:
                self.text_engine.start_text("Too lazy, Eh?")
            elif name in ("A", "AAAAAAA", "HUMAN", "PERSON"):
                self.text_engine.start_text('Not very creative,^wait500 are you?')
            elif name in ("TIGO", "JORIS", "QUINTEN", "CARPET", "JOSIAH", "EVERAN", "AMY", "ETHAN"):
                self.text_engine.start_text('Ah yes, ^wait250my creators')
            else:
                self.text_engine.start_text(f'"{name}."')

            self._dialog_started = True

        if self.is_teto:
            self.teto_text_engine.draw(125, 70, (255, 255, 255), size=26)
            if self.teto_text_engine.finished:
                self.wait_timer += dt
                if self.wait_timer >= 1.5:
                    sys.exit(0)
            return False

        self.text_engine.draw(125, 70, (255, 255, 255), size=26)
        if self.text_engine.finished:
            return self._advance_after_wait(dt, 1.5)
        return False

    def draw_creator_prompt(self, dt):
        self.text_engine.update(dt)
        self.teto_text_engine.update(dt)

        

        if not self._dialog_started:
            self.text_engine.start_text(
                'And what about ^wait1000^special^color(255,0,0)^shake7you^endspecial?'
            )
            self._dialog_started = True

        self.text_engine.draw(125, 70, (255, 255, 255), size=26)
        self.teto_text_engine.draw(125, 70, (255, 255, 255), size=26)

        if self.text_engine.finished:
            return self._advance_after_wait(dt, 1.5)
        return False

    def draw_final_dialog(self, dt):
        self.text_engine.update(dt)

        lines = [
            "Thank you for your time",
            f"you may now wake up,&^wait1000{self.chara_name}"
        ]

        if self.dialog_index >= len(lines):
            self.save_names()
            return True

        if not self._dialog_started:
            self.text_engine.start_text(lines[self.dialog_index])
            self._dialog_started = True

        if self.text_engine.finished and self._advance_after_wait(dt, 1.5):
            self.dialog_index += 1

        self.text_engine.draw(125, 70, (255, 255, 255), size=26)
        return False

    # --------------------------------------------------
    # letter-select screen
    # --------------------------------------------------

    def draw_alfabet(self, dt):
        self.text_engine.draw(125, 70, (255, 255, 255), size=26)

        # smooth continuous up/down bob (sine has zero velocity at each end,
        # so there's no snap at the top/bottom like a linear bounce would have)
        self.timer_y += dt
        bob = (math.sin(self.timer_y * self.bob_speed) * 0.5 + 0.5) * self.max_y_height

        if self.step == 3:
            # webcam_surface = self._get_webcam_surface()
            # self.screen.blit(webcam_surface if webcam_surface is not None else self.player_img, (150, 415 + bob))
            # We have 2 somehow make a better hand
            # self.screen.blit(self.hand_point_img, (150, 415 + bob))
            self.screen.blit(self.player_img, (150, 415 + bob))
        else:
            self.screen.blit(self.player_img, (150, 415 + bob))

        padding = 8

        # letters
        for idx, letter in enumerate(self.alfabet):
            col, row = idx % self.grid_cols, idx // self.grid_cols
            self._draw_text(letter, self._cell_pos(col, row))

        # buttons
        for i, btn in enumerate(self.buttons):
            pos_x = self.start_x + i * self.cell_size + (200 * i)
            pos_y = self.start_y + self.button_row * self.cell_size
            self._draw_text(btn, (pos_x, pos_y))

        # typed letters + placeholders
        for i in range(self.max_letters):
            pos = (self.start_x + i * self.cell_size, self.start_y - 100)
            if i < len(self.selected_letters):
                self._draw_text(self.selected_letters[i], pos)
            else:
                self._draw_text("_", pos)

        # cursor box
        if self.cursor_y == self.button_row:
            label = self.buttons[self.cursor_x]
            pos_x = self.start_x + self.cursor_x * self.cell_size + (200 * self.cursor_x)
            pos_y = self.start_y + self.cursor_y * self.cell_size
        else:
            label = self.alfabet[self.cursor_y * self.grid_cols + self.cursor_x]
            pos_x, pos_y = self._cell_pos(self.cursor_x, self.cursor_y)

        text_w, text_h = self.font.size(label)
        cursor = pygame.Rect(0, 0, text_w + padding, text_h + padding)
        cursor.center = (pos_x + text_w / 2 - 3, pos_y + text_h / 2 + 2)
        pygame.draw.rect(self.screen, (255, 0, 0), cursor, 3)

    # --------------------------------------------------
    # misc
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

    def save_names(self):
        data = {
            "character_name": self.chara_name,
            "creator_name": self.creator_name
        }
        path = self.file_loader.load("names.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    # --------------------------------------------------
    # main loop
    # --------------------------------------------------

    def _handle_keydown(self, event):
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
                elif self.selected_letters:
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
                if idx < len(self.alfabet) and len(self.selected_letters) < self.max_letters:
                    self.selected_letters.append(self.alfabet[idx])

        self._clamp_cursor()

    def draw(self, dt):
        clock = pygame.time.Clock()

        path = self.file_loader.load("names.json")
        print("SAVE PATH =", path)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.chara_name = data.get("character_name", self.chara_name)
                self.creator_name = data.get("creator_name", self.creator_name)
                return
            except Exception:
                pass

        while True:
            dt = clock.tick(60) / 1000
            self.screen.fill((0, 0, 0))

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._register_quit()
                    pygame.quit()
                    sys.exit(0)

                if event.type == pygame.KEYDOWN and self.step in (1, 3):
                    self._handle_keydown(event)

            if self.step == -2:
                self.black_timer += dt
                if self.black_timer >= 2.0:
                    self.step = -1

            elif self.step == -1:
                self.update_cursor(dt)
                self.draw_flicker_cursor()

            elif self.step == 0:
                self.draw_intro(dt)

            elif self.step in (1, 3):
                self.draw_alfabet(dt)

            elif self.step == 2:
                if self.draw_name_result(dt, self.chara_name):
                    self.step = 2.5

            elif self.step == 2.5:
                if self.draw_creator_prompt(dt):
                    self.step = 3

            elif self.step == 4:
                if self.draw_name_result(dt, self.creator_name):
                    self.dialog_index = 0
                    self.step = 5

            elif self.step == 5:
                if self.draw_final_dialog(dt):
                    print("huhhhh")
                    return

            pygame.display.flip()