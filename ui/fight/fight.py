import importlib.util
import math
import os
import sys
from typing import Dict, Optional, Tuple

import pygame

from assetsLoader import Loader
from bulletengine.bulletengine import BulletHellEngine
from ui.boxEngine.boxengine import BoxEngine
from ui.textengine.textengine import TextEngine

import BtnHandeler

import cutscenes.loader as CutsceneLoaderModule

class dummyfight:
    def __init__(self):
        pass
    def update(self, dt, x):
        pass
    def draw(self, screen):
        pass


def get_base_path() -> str:
    if hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS

    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)

    return os.path.abspath(".")


def load_fight_module(fight_name: str):
    base_path = get_base_path()
    fight_path = os.path.join(base_path, "ui", "fight", "fights", f"{fight_name}.py")

    if not os.path.exists(fight_path):
        print(f"[FightLoader] Missing fight file: {fight_path}")
        return None

    module_name = f"fight_{fight_name}"

    try:
        spec = importlib.util.spec_from_file_location(module_name, fight_path)
        if spec is None or spec.loader is None:
            print(f"[FightLoader] Could not create spec for {fight_name}")
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as e:
        print(f"[FightLoader] Failed to load fight {fight_name}: {e}")
        return None

    if not hasattr(module, "run"):
        print(f"[FightLoader] Missing 'run()' in {fight_name}.py")
        return None

    return module


class Fight:
    TURN_PLAYER = 0
    TURN_ENEMY = 1
    UI_SCALE = 4

    @property
    def current_turn(self):
        return self._current_turn

    @current_turn.setter
    def current_turn(self, new_turn):
        if not hasattr(self, "_current_turn"):
            self._current_turn = new_turn
            return

        if new_turn == self._current_turn:
            return

        self.turn_transition_active = True
        self.turn_transition_t = 0.0
        self.turn_transition_from = self._current_turn
        self.turn_transition_to = new_turn

    def __init__(self, screen, true_screen, player, world):
        self.renderer = screen
        self.screen = true_screen
        self.world = world
        self.player = player

        self.module = None
        self.running = False

        self._current_turn = self.TURN_PLAYER
        self.turn_transition_active = False
        self.turn_transition_t = 0.0
        self.turn_transition_duration = 0.5
        self.turn_transition_from = self.TURN_PLAYER
        self.turn_transition_to = self.TURN_PLAYER

        self.black_overlay = pygame.Surface((1280,720), pygame.SRCALPHA)
        self.death_timer = 0

        self.current_section = 1
        self.current_talk_section = 1
        self.current_selected_btn = 0

        self.text_engine = TextEngine()
        self.hp_text_engine = TextEngine()
        self.item_text_engine = TextEngine()

        self.alpha = 0

        self.bbox = False
        self.render_text_bbox = True
        self.show_item_shit = False
        self.lock_menumove = False
        self.item_text = ""
        self.item_mode = False
        self.talk_lock_stage = 0
        self.is_btn_hold = False
        self.text_finished_EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE = False
        self.text_finished_last_frame = False

        self._fight_text_cache: Dict[Tuple[str, int], str] = {}
        self._big_text_cache: Optional[str] = None
        self._big_text_mtime: Optional[float] = None
        self._monster_scaled_cache = None
        self._monster_scaled_source = None
        self._hp_label_text = None

        loader = Loader("ui/fight/fight_assets")

        self.btn_images = []
        for name in ["btn_1.png", "btn_2.png", "btn_3.png"]:
            path = loader.load(name)
            img = pygame.image.load(path).convert_alpha()
            self.btn_images.append(
                pygame.transform.scale(
                    img,
                    (img.get_width() * self.UI_SCALE, img.get_height() * self.UI_SCALE),
                )
            )

        self.select_btn_images = []
        for name in ["btn_4.png", "btn_5.png", "btn_6.png","btn_7.png", "btn_8.png", "btn_9.png"]:
            path = loader.load(name)
            img = pygame.image.load(path).convert_alpha()
            self.select_btn_images.append(
                pygame.transform.scale(
                    img,
                    (img.get_width() * self.UI_SCALE, img.get_height() * self.UI_SCALE),
                )
            )

        # Cached bright/white versions for the tiny flash effect when switching buttons.
        self.btn_flash_images = [self._make_white_flash(img) for img in self.btn_images]
        self.select_btn_flash_images = [
            self._make_white_flash(img) for img in self.select_btn_images
        ]

        self.btn_switch_flash_duration = 1.0 / 60.0
        self.btn_switch_flash_timer = 0.0

        self.monster_loader = Loader("sprites/")
        self.monster_image = None

        self.monster_def = 10
        self.monster_atk = 8
        self.monster_max_hp = 150
        self.monster_hp = 150

        self.monster_base_x = 128
        self.monster_base_y = 38
        self.monster_x = self.monster_base_x
        self.monster_y = self.monster_base_y

        self.hit_timer = 0.0
        self.hit_duration = 0.1
        self.hit_power = 60

        self.player_atk = self.player.atk
        self.player_def = self.player.defense
        self.player_speed = 200

        self.active_cutscene = False

        self.dt = 0
        self.select_btn_animation_timer = 0

        self.player_x, self.player_y = 533, 150 + 280
        self.speed_X, self.speed_Y = 0.0, 0.0
        self.player_max_hp = 100

        self.dialogue_box = pygame.Surface((240 * self.UI_SCALE, 45 * self.UI_SCALE)).convert_alpha()
        self.dialogue_box.fill((0, 0, 0))
        pygame.draw.rect(self.dialogue_box, (255, 255, 255), self.dialogue_box.get_rect(), 8)

        self.attack_box = pygame.Surface((90 * self.UI_SCALE, 90 * self.UI_SCALE)).convert_alpha()
        self.attack_box.fill((0, 0, 0))
        pygame.draw.rect(self.attack_box, (255, 255, 255), self.attack_box.get_rect(), 8)

        self.bullet_engine = BulletHellEngine(max_bullets=1000, fight_loader=self)

        try:
            self.boxEngine = BoxEngine(world_loader=world, preset="textbox_fights")
            self.boxEngine.create_box((760, 90, 100, 100))
        except Exception as e:
            print(f"Error while loading boxengine {e}")
            self.boxEngine = None

        self.btnHandeler = BtnHandeler.btnHandeler()

        self.hp_text = f"{self.player.hp}/100"
        self.hp_text_dirty = True
        self._last_hp_text = None

        self.bullet_timer = 0.0
        self.turn_timer = 0.0
        self.turn_duration = 15.0
        self.bullet_interval = 0.5
        self.hammer_timer = 0.0
        self.hat_timer = 0.0

        self.last_hammer_cycle = -1
        self.hammer_dropped_this_cycle = False
        self.pending_hammer_x = 0

        self.last_hat_cycle = -1
        self.hat_exploded_this_cycle = True
        self.pending_hat_x = 0
        self.pending_hat_y = 0
        self.pending_hat_id = None
        self.pending_exp_id = None

        self.idx = 0
    def _make_white_flash(self, surface):
        flash = surface.copy()
        flash.fill((255, 255, 255), special_flags=pygame.BLEND_RGB_MAX)
        return flash

    def _ease(self, t):
        return t * t * (3 - 2 * t)

    def _lerp(self, a, b, t):
        return a + (b - a) * t

    def _lerp_rect(self, r1, r2, t):
        return pygame.Rect(
            int(self._lerp(r1.x, r2.x, t)),
            int(self._lerp(r1.y, r2.y, t)),
            max(1, int(self._lerp(r1.w, r2.w, t))),
            max(1, int(self._lerp(r1.h, r2.h, t))),
        )

    def _menu_box_rect(self):
        return pygame.Rect(
            40 * self.UI_SCALE,
            84 * self.UI_SCALE,
            240 * self.UI_SCALE,
            45 * self.UI_SCALE,
        )

    def _battle_box_rect(self):
        where_to_put_me = int((1280 / 2) - (self.attack_box.get_width() / 2))
        return pygame.Rect(
            where_to_put_me,
            int(84 * self.UI_SCALE),
            self.attack_box.get_width(),
            self.attack_box.get_height(),
        )

    def _draw_box_transition(self, screen):
        start_rect = self._menu_box_rect() if self.turn_transition_from == self.TURN_PLAYER else self._battle_box_rect()
        end_rect = self._menu_box_rect() if self.turn_transition_to == self.TURN_PLAYER else self._battle_box_rect()

        t = self._ease(min(1.0, self.turn_transition_t / self.turn_transition_duration))
        rect = self._lerp_rect(start_rect, end_rect, t)

        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        surf.fill((0, 0, 0))
        pygame.draw.rect(surf, (255, 255, 255), surf.get_rect(), 8)
        screen.blit(surf, rect.topleft)

    def _load_big_text(self) -> str:
        base_path = get_base_path()
        text_file = os.path.join(base_path, "ui", "fight", "BIG_TEXT.TXT")

        if not os.path.exists(text_file):
            return ""

        try:
            mtime = os.path.getmtime(text_file)
            if self._big_text_cache is None or self._big_text_mtime != mtime:
                with open(text_file, "r", encoding="utf-8") as f:
                    self._big_text_cache = f.read()
                self._big_text_mtime = mtime
        except Exception as e:
            print(f"[Fight] Error loading BIG_TEXT.TXT: {e}")
            return ""

        return self._big_text_cache or ""

    def parse_fight_text(self, text_content: str, identifier: str, section: int) -> str:
        self.bbox = False
        section_marker_start = f"(SECTION_{section})"
        section_marker_end = f"(ENDSECTION_{section})"

        search_token = f"{identifier} ="
        identifier_start = text_content.find(search_token)
        if identifier_start == -1:
            return ""

        next_identifier_pos = len(text_content)
        remaining_text = text_content[identifier_start + len(search_token) :]

        for line in remaining_text.splitlines():
            stripped = line.strip()
            if (
                " = " in line
                and stripped
                and not stripped.startswith("[")
                and not stripped.startswith("{")
                and not stripped.startswith("(")
            ):
                next_identifier_pos = (
                    identifier_start
                    + len(search_token)
                    + text_content[identifier_start + len(search_token) :].find(line)
                )
                break

        identifier_block = text_content[identifier_start:next_identifier_pos]

        section_start = identifier_block.find(section_marker_start)
        section_end = identifier_block.find(section_marker_end)
        if section_start == -1 or section_end == -1:
            return ""

        section_text = identifier_block[
            section_start + len(section_marker_start) : section_end
        ]

        if "IN_BBOX" in section_text:
            self.bbox = True

        lines = []
        for line in section_text.splitlines():
            line = line.strip()
            if (
                line
                and not line.startswith("[")
                and not line.startswith("{")
                and not line.startswith("IN_BBOX")
            ):
                lines.append(line)

        return "".join(lines)

    def _get_cached_section(self, identifier: str, section: int) -> str:
        key = (identifier, section)
        if key in self._fight_text_cache:
            return self._fight_text_cache[key]

        text_content = self._load_big_text()
        if not text_content:
            return ""

        parsed = self.parse_fight_text(text_content, identifier, section)
        self._fight_text_cache[key] = parsed
        return parsed

    def load_fight(self, fight_name, idx):
        self.module = load_fight_module(fight_name)

        if self.module and hasattr(self.module, "init"):
            self.module.init(self)

        self.running = True
        self.load_section_text()
        self.idx = idx
        return self

    def load_section_text(self):
        if not hasattr(self, "fight_identifier") or not hasattr(self, "current_section"):
            return

        section_text = self._get_cached_section(self.fight_identifier, self.current_section)
        if section_text:
            self.item_mode = False
            self.item_text = ""
            self.text_engine.start_text(section_text, self.fight_identifier)
            self.text_finished_EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE = False
            self.render_text_bbox = True

    def load_talk_text(self):
        if not hasattr(self, "fight_identifier") or not hasattr(self, "current_talk_section"):
            return

        section_text = self._get_cached_section(
            f"{self.fight_identifier}_talks", self.current_talk_section
        )
        if section_text:
            self.item_mode = False
            self.item_text = ""
            self.text_engine.start_text(section_text, self.fight_identifier)
            self.text_finished_EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE = False
            self.render_text_bbox = True

    def start_talk_flow(self):
        self.current_selected_btn = 2
        self.lock_menumove = True
        self.talk_lock_stage = 1
        self.render_text_bbox = True
        self.load_talk_text()

    def show_item_menu(self):
        self.show_item_shit = True
        self.item_mode = True

        item_names = [item["short_name"] for item in self.player.items]
        self.item_text_engine.start_choices("", item_names)

        self.item_text = "& &".join(item_names)
        if not self.item_text:
            self.item_text = "No items."
            self.item_text_engine.start_text(self.item_text, "")

    def close_item_menu(self):
        self.show_item_shit = False
        self.item_mode = False
        self.item_text = ""
        self.item_text_engine.finished = True
        self.load_talk_text()

    def update(self, dt, joystick=None):
        bullet_engine = self.bullet_engine
        module = self.module
        btns = self.btnHandeler
        self.dt = dt

        if self.btn_switch_flash_timer > 0.0:
            self.btn_switch_flash_timer = max(0.0, self.btn_switch_flash_timer - dt)

        if self.turn_transition_active:
            self.turn_transition_t += dt
            if self.turn_transition_t >= self.turn_transition_duration:
                self.turn_transition_active = False
                self._current_turn = self.turn_transition_to

        bullet_engine.update(
            dt,
            self.player_x,
            self.player_y,
            7,
            left=-500,
            right=1280 + 500,
            top=-500,
            bottom=720 + 500,
            on_hit=self.on_bullet_hit,
        )

        if module is None:
            return

        if not self.text_engine.finished:
            self.text_engine.update(dt)

        if self.item_mode and not self.item_text_engine.finished:
            self.item_text_engine.update(dt)

        if not self.hp_text_engine.finished:
            self.hp_text_engine.update(dt)

        if self.current_turn == self.TURN_PLAYER:
            if not self.turn_transition_active:
                if self.lock_menumove:
                    if self.talk_lock_stage == 1 and btns.get_btn_down("z"):
                        self.lock_menumove = False
                        self.talk_lock_stage = 0
                        self.current_turn = self.TURN_ENEMY
                        self.text_engine.finished = True
                        self.text_finished_EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE = True
                elif self.item_mode:
                    raw_keys = pygame.key.get_pressed()
                    choice = self.item_text_engine.handle_choice_input(raw_keys, None)

                    if choice is not None and btns.get_btn_down("z"):
                        self.player.handle_item_used(choice)
                        self.show_item_menu()

                    if btns.get_btn_down("x"):
                        self.close_item_menu()
                else:
                    old_selected_btn = self.current_selected_btn

                    if btns.get_btn_down("left"):
                        self.current_selected_btn -= 1
                    elif btns.get_btn_down("right"):
                        self.current_selected_btn += 1

                    self.current_selected_btn %= len(self.btn_images)

                    if self.current_selected_btn != old_selected_btn:
                        self.btn_switch_flash_timer = self.btn_switch_flash_duration

                    if btns.get_btn_down("z"):
                        if self.current_selected_btn == 0 and self.monster_hp > 0:
                            self.attack_monster()
                        elif self.current_selected_btn == 1:
                            self.show_item_menu()
                        elif self.current_selected_btn == 2:
                            self.start_talk_flow()

        elif self.current_turn == self.TURN_ENEMY:
            if not self.turn_transition_active and self.player.hp > 0:
                self.speed_X = 0
                self.speed_Y = 0

                if btns.get_btn_pressed("left"):
                    self.speed_X = -self.player_speed
                elif btns.get_btn_pressed("right"):
                    self.speed_X = self.player_speed

                if btns.get_btn_pressed("up"):
                    self.speed_Y = -self.player_speed
                elif btns.get_btn_pressed("down"):
                    self.speed_Y = self.player_speed

                self.player_x += self.speed_X * dt
                self.player_y += self.speed_Y * dt

                self.player_x = max(460 + 7, min(820 - 7, self.player_x))
                self.player_y = max(336 + 7, min(696 - 7, self.player_y))

        try:
            module.run(self, dt, joystick)
        except Exception as e:
            print(f"[Fight] Error running fight module: {e}")

        hp_text = f"{self.player.hp}/100"
        if hp_text != self._last_hp_text:
            self._last_hp_text = hp_text
            self.hp_text = hp_text
            self.hp_text_engine.start_text(hp_text, "")

    def attack_monster(self):
        self.current_turn = self.TURN_ENEMY
        self.text_engine.finished = True
        self.text_finished_EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE = True

        if self.monster_max_hp <= 0:
            return

        hp_ratio = self.monster_hp / self.monster_max_hp
        missing_hp_ratio = 1 - hp_ratio

        base = max(1, self.player_atk - self.monster_def)
        damage = (
            base
            * (1 + (self.player_atk / (self.player_atk + 100)))
            * (100 / (100 + self.monster_def))
            * (1 + missing_hp_ratio * 0.75)
            * (1 + math.sqrt(base) / 60)
        )

        damage = int(damage)
        self.monster_hp = max(0, self.monster_hp - damage)
        self.hp_text = f"{self.player.hp}/100"
        self.hp_text_dirty = True

        if self.monster_hp <= 0:
            if hasattr(self.module, "killed") and self.module.killed(self, 0.0, None) == 1:
                self.end_fight(reason=0)

        self.hit_timer = self.hit_duration
        self.hit_power = min(100, 20 + damage)

    def end_fight(self, reason=0):
        print(f"[Fight] end_fight called, reason={reason}")

        self.running = False
        self.bullet_engine.clear()

        if self.module is not None and hasattr(self.module, "on_end"):
            try:
                self.module.on_end(self, reason)
            except Exception as e:
                print(f"[Fight] on_end error: {e}")

        self.module = None

        player = self.player
        if player is not None:
            try:
                player.active_fight = None
                player.frozen = False

                if reason == 0: #Won!
                    music_loader = Loader("music")
                    
                    music_path = music_loader.load(self.player.bg_music_name)
                    
                    pygame.mixer.music.load(music_path)
                    
                    pygame.mixer.music.play(-1)

                if reason == 3:
                    if hasattr(player, "die"):
                        player.die()
                    else:
                        player.dead = True
                else:
                    player.can_move = True
            except Exception as e:
                print(f"[Fight] Could not apply player state: {e}")

    def spawn_bullet(
        self,
        x,
        y,
        size,
        color,
        damage,
        rotation,
        speed=300,
        type="dot",
        angular_velocity=0.0,
    ):
        return self.bullet_engine.spawn_at_angle(
            x=x,
            y=y,
            angle=rotation,
            speed=speed,
            size=size,
            color=color,
            bullet_type=type,
            lifetime=float("inf"),
            angular_velocity=angular_velocity,
        )

    def on_bullet_hit(self, bullet_idx):
        base = max(1, self.monster_atk - self.player_def)
        damage = max(1, int(base * (1 + self.monster_atk / (self.monster_atk + 100))))

        self.player.hp = max(0, self.player.hp - damage)

    def _get_scaled_monster(self):
        if self.monster_image is None:
            return None

        if self._monster_scaled_source is self.monster_image and self._monster_scaled_cache is not None:
            return self._monster_scaled_cache

        self._monster_scaled_source = self.monster_image
        self._monster_scaled_cache = pygame.transform.scale(
            self.monster_image,
            (
                int(self.monster_image.get_width() * self.UI_SCALE),
                int(self.monster_image.get_height() * self.UI_SCALE),
            ),
        )
        return self._monster_scaled_cache

    def _update_hp_label(self):
        hp_text = f"{self.player.hp}/{self.player.max_hp}"
        if hp_text == self._hp_label_text:
            return

        self._hp_label_text = hp_text
        self.hp_text_engine.start_text(hp_text, "")
        self.hp_text_engine.char_index = 99
        self.hp_text_engine.finished = True

    def draw_hp_label(self, screen, box_rect, hp_text):
        self._update_hp_label()
        self.hp_text_engine.draw(
            x=box_rect.right + 10,
            y=box_rect.top + 4,
            text_color=(255, 255, 255),
            choice_color=(180, 180, 180),
            highlight_color=(255, 255, 0),
            size=12,
            surface=screen,
        )

    def draw(self, screen=None):
        if screen is None:
            screen = self.screen

        screen.fill((0, 0, 0))
        if self.player.hp > 0:
            turn = self.current_turn
        else:
            turn = self.TURN_ENEMY

        if self.turn_transition_active:
            self._draw_box_transition(screen)
            self.bullet_engine.clear()
            
        elif turn == self.TURN_PLAYER:
            base_x = 40 * self.UI_SCALE
            base_y = 145 * self.UI_SCALE
            step_x = 95 * self.UI_SCALE

            for i, btn in enumerate(self.btn_images):
                x = base_x + i * step_x
                screen.blit(btn, (x, base_y))

            for i, btn in enumerate(self.select_btn_images):
                if self.current_selected_btn == i and not self.show_item_shit:
                    x = base_x + i * step_x
                    if self.btn_switch_flash_timer > 0.0:
                        flash_img = self.select_btn_flash_images[i]
                        # screen.blit(flash_img, (x, base_y))
                    else:
                        self.select_btn_animation_timer += self.dt
                        if i <= 2:
                            frame = int(self.select_btn_animation_timer * 3) % 2
                            screen.blit(self.select_btn_images[frame * 3 + i], (x, base_y))

            screen.blit(self.dialogue_box, (40 * self.UI_SCALE, 84 * self.UI_SCALE))
        else:
            where_to_put_me = int((1280 / 2) - (self.attack_box.get_width() / 2))
            attack_box_rect = pygame.Rect(
                where_to_put_me,
                int(84 * self.UI_SCALE),
                self.attack_box.get_width(),
                self.attack_box.get_height(),
            )
            screen.blit(self.attack_box, (attack_box_rect.x, attack_box_rect.y))

        monster_scaled = self._get_scaled_monster()
        if monster_scaled:
            screen.blit(
                monster_scaled,
                (int(self.monster_x * self.UI_SCALE), int(self.monster_y * self.UI_SCALE)),
            )

        self.bullet_engine.draw(screen)

        if turn == self.TURN_ENEMY:
            if self.player.hp <= 0:
                if self.alpha >= 255:
                    self.alpha = 255
                else:
                    self.alpha += 127*self.dt

                self.death_timer += self.dt
                if self.death_timer >= 1.5 and not self.death_timer >= 999999999: #seconds
                    try:
                        self.active_cutscene = CutsceneLoaderModule.CutsceneLoader()
                        self.curr_animation = "Idle"
                        self.active_cutscene.world = self.world
                        self.active_cutscene.event = None
                        self.active_cutscene.player = self.player
                        self.active_cutscene.load("death", None)
                        self.active_cutscene.trigger_idx = 999999999999999999999999
                        self.in_death_scene = True
                        self.death_timer = 99999999999999999999999999
                        music_loader = Loader("music")
                        
                        music_path = music_loader.load(self.player.bg_music_name)
                        
                        pygame.mixer.music.load(music_path)
                        
                        pygame.mixer.music.play(-1)
                    except Exception as e:
                        print("Error loading cutscene:", e)
                        self.active_cutscene = None
                    
            screen.blit(self.black_overlay, (0,0))
            self.black_overlay.fill((0, 0, 0, round(self.alpha % 256)))
            if not  self.turn_transition_active:
                pygame.draw.circle(
                    screen, (0, 255, 0), (int(self.player_x), int(self.player_y)), 7
                )

        self.draw_text(screen)

        total_length = 100
        hp_total_rect = pygame.Rect((10, 10), (total_length, 30))
        hp_width = int((self.player.hp / self.player.max_hp) * total_length)
        hp_rect = pygame.Rect(10, 10, hp_width, 30)
        pygame.draw.rect(screen, (255, 0, 0), hp_total_rect)
        pygame.draw.rect(screen, (240, 236, 7), hp_rect)

        self.draw_hp_label(screen, hp_total_rect, self.hp_text)

    def draw_text(self, screen=None):
        if screen is None:
            screen = self.screen

        if self.turn_transition_active:
            return

        if self.item_mode:
            self.item_text_engine.draw(
                x=180,
                y=356,
                text_color=(255, 255, 255),
                choice_color=(180, 180, 180),
                highlight_color=(255, 255, 0),
                size=12,
                surface=screen,
            )
            return

        if self.bbox:
            if self.current_turn == self.TURN_PLAYER:
                self.text_engine.draw(
                    x=180,
                    y=356,
                    text_color=(255, 255, 255),
                    choice_color=(180, 180, 180),
                    highlight_color=(255, 255, 0),
                    size=12,
                    surface=screen,
                )
        else:
            if self.current_turn == self.TURN_ENEMY:
                if self.btnHandeler.get_btn_pressed("y") and self.text_engine.finished:
                    self.render_text_bbox = False

                if self.render_text_bbox and self.boxEngine is not None:
                    self.boxEngine.draw(screen=screen, with_btns=False)
                    self.text_engine.draw(
                        x=760 + 10,
                        y=90 + 20,
                        text_color=(0, 0, 0),
                        choice_color=(180, 180, 180),
                        highlight_color=(255, 255, 0),
                        size=12,
                        surface=screen,
                    )

        if self.active_cutscene:
            self.active_cutscene.update(self.dt, self.player)
            self.player._triggered_once.discard(self.idx)
            self.active_cutscene.draw(screen)
            self.player.active_cutscene = dummyfight()
