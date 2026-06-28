import importlib.util
import math
import os
import sys

import pygame

from assetsLoader import Loader
from bulletengine.bulletengine import BulletHellEngine
from ui.boxEngine.boxengine import BoxEngine
from ui.textengine.textengine import TextEngine


def get_base_path():
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

    def __init__(self, screen, true_screen, player, world):
        self.renderer = screen
        self.screen = true_screen
        self.world = world

        self.module = None
        self.running = False

        self.current_turn = self.TURN_PLAYER
        self.current_section = 1
        self.current_selected_btn = 0

        self.player = player
        self._prev_keys = pygame.key.get_pressed()

        self.text_engine = TextEngine()

        # Legacy flags / compatibility
        self.text_finished_EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE = False
        self.bbox = False
        self.render_text_bbox = True
        self.show_item_shit = False
        self.lock_menumove = False

        # Item dialogue state
        self.item_text = ""
        self.item_mode = False

        # Buttons
        loader = Loader("ui/fight/fight_assets")

        self.btn_images = []
        for name in ["btn_1.png", "btn_2.png", "btn_3.png"]:
            path = loader.load(name)
            img = pygame.image.load(path).convert_alpha()
            self.btn_images.append(img)

        self.select_btn_images = []
        for name in ["btn_4.png", "btn_5.png", "btn_6.png"]:
            path = loader.load(name)
            img = pygame.image.load(path).convert_alpha()
            self.select_btn_images.append(img)

        # Monster
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

        # Teleport animation / hit animation
        self.hit_timer = 0
        self.hit_duration = 0.1
        self.hit_power = 60

        # Player
        self.player_atk = self.player.atk
        self.player_def = self.player.defense
        self.player_speed = 200

        self.player_x, self.player_y = 533, 150 + 280
        self.speed_X, self.speed_Y = 0, 0

        self.player_max_hp = 100
        self.player_hp = 100

        # Black box with white outline for dialogue
        self.dialogue_box = pygame.Surface((240, 45))
        self.dialogue_box.fill((0, 0, 0))

        self.attack_box = pygame.Surface((90, 90))
        self.attack_box.fill((0, 0, 0))

        # Bullet engine
        self.bullet_engine = BulletHellEngine(max_bullets=1000, fight_loader=self)

        # Box engine
        try:
            self.boxEngine = BoxEngine(world_loader=world, preset="textbox_fights")
            self.boxEngine.create_box((760, 90, 100, 100))
        except Exception as e:
            print(f"Error while loading boxengine {e}")
            self.boxEngine = None

    def parse_fight_text(self, text_content: str, identifier: str, section: int) -> str:
        """Parse BIG_TEXT.txt file and extract text for a specific identifier and section."""
        self.bbox = False
        section_marker_start = f"(SECTION_{section})"
        section_marker_end = f"(ENDSECTION_{section})"

        if f"{identifier} =" not in text_content:
            return ""

        identifier_start = text_content.find(f"{identifier} =")
        if identifier_start == -1:
            return ""

        next_identifier_pos = len(text_content)
        remaining_text = text_content[identifier_start + len(f"{identifier} =") :]

        for line in remaining_text.split("\n"):
            if (
                " = " in line
                and not line.strip().startswith("[")
                and not line.strip().startswith("{")
                and not line.strip().startswith("(")
            ):
                next_identifier_pos = (
                    identifier_start
                    + len(f"{identifier} =")
                    + text_content[identifier_start + len(f"{identifier} =") :].find(line)
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
        for line in section_text.split("\n"):
            line = line.strip()
            if (
                line
                and not line.startswith("[")
                and not line.startswith("{")
                and not line.startswith("IN_BBOX")
            ):
                lines.append(line)

        return "\n".join(lines)

    def load_fight(self, fight_name):
        self.module = load_fight_module(fight_name)

        if self.module:
            if hasattr(self.module, "init"):
                self.module.init(self)

        self.running = True
        print("PPPP")  # Teto won 100%

        self.load_section_text()
        return self

    def load_section_text(self):
        """Load and display text for the current section from BIG_TEXT.TXT."""
        if not hasattr(self, "fight_identifier") or not hasattr(self, "current_section"):
            return

        base_path = get_base_path()
        text_file = os.path.join(base_path, "ui", "fight", "BIG_TEXT.TXT")

        if not os.path.exists(text_file):
            return

        try:
            with open(text_file, "r", encoding="utf-8") as f:
                text_content = f.read()

            section_text = self.parse_fight_text(
                text_content, self.fight_identifier, self.current_section
            )

            if section_text:
                self.item_mode = False
                self.item_text = ""
                self.text_engine.start_text(section_text, self.fight_identifier)

        except Exception as e:
            print(f"[Fight] Error loading section text: {e}")

    def show_item_menu(self):
        self.show_item_shit = True
        self.item_mode = True

        item_names = []
        for item in self.player.items:
            print(item["name"])
            item_names.append(item["short_name"])

        self.item_text = " & ".join(item_names)
        if not self.item_text:
            self.item_text = "No items."

        self.text_engine.start_text(self.item_text, "")

    def close_item_menu(self):
        self.show_item_shit = False
        self.item_mode = False
        self.item_text = ""
        self.text_engine.finished = True

    def update(self, dt, joystick=None):
        self.bullet_engine.update(
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

        if self.module is None:
            return

        keys = pygame.key.get_pressed()

        if self.current_turn == self.TURN_PLAYER and not self.lock_menumove:
            if self.item_mode:
                if keys[pygame.K_z] and not self._prev_keys[pygame.K_z]:
                    self.close_item_menu()
            else:
                if keys[pygame.K_LEFT] and not self._prev_keys[pygame.K_LEFT]:
                    self.current_selected_btn -= 1
                elif keys[pygame.K_RIGHT] and not self._prev_keys[pygame.K_RIGHT]:
                    self.current_selected_btn += 1

                self.current_selected_btn %= len(self.btn_images)

                if keys[pygame.K_z] and not self._prev_keys[pygame.K_z]:
                    if self.current_selected_btn == 0 and self.monster_hp > 0:
                        self.attack_monster()
                    elif self.current_selected_btn == 1:
                        self.show_item_menu()

        if self.current_turn == self.TURN_ENEMY:
            if keys[pygame.K_LEFT]:
                self.speed_X = -self.player_speed
            elif keys[pygame.K_RIGHT]:
                self.speed_X = self.player_speed
            else:
                self.speed_X = 0

            if keys[pygame.K_UP]:
                self.speed_Y = -self.player_speed
            elif keys[pygame.K_DOWN]:
                self.speed_Y = self.player_speed
            else:
                self.speed_Y = 0

            self.player_x += self.speed_X * dt
            self.player_y += self.speed_Y * dt

            attack_box_left = 460 + 7
            attack_box_right = 820 - 7
            attack_box_top = 336 + 7
            attack_box_bottom = 696 - 7

            self.player_x = max(attack_box_left, min(attack_box_right, self.player_x))
            self.player_y = max(attack_box_top, min(attack_box_bottom, self.player_y))

        try:
            self.module.run(self, dt, joystick)
        except Exception as e:
            print(f"[Fight] Error running fight module: {e}")

        self._prev_keys = keys

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
        self.monster_hp -= damage
        self.monster_hp = max(0, self.monster_hp)

        print(f"Damage: {damage} | Monster HP: {self.monster_hp}")

        if self.monster_hp <= 0:
            if hasattr(self.module, "killed") and self.module.killed(self, 0.0, None) == 1:
                self.end_fight(reason=0)

        self.hit_timer = self.hit_duration
        self.hit_power = min(100, 20 + damage)

    def end_fight(self, reason=0):
        """reason 0 = monster dead, reason 1 = spared reason 2 = fled reason 3 = player dead"""
        print(f"[Fight] end_fight called, reason={reason}")

        self.running = False
        self.bullet_engine.clear()

        if self.module is not None:
            if hasattr(self.module, "on_end"):
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
        """Spawn a bullet with direction based on rotation (degrees)."""
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
        """Callback when a bullet hits the player."""
        base = max(1, self.monster_atk - self.player_def)
        damage = max(1, int(base * (1 + self.monster_atk / (self.monster_atk + 100))))

        self.player_hp -= damage
        self.player_hp = max(0, self.player_hp)

        print(f"Player hit! Damage: {damage} | Player HP: {self.player_hp}")

    def draw(self, screen=None):
        if screen is None:
            screen = self.screen

        scale = 4
        screen.fill((0, 0, 0))

        if self.current_turn == self.TURN_PLAYER:
            for i, btn in enumerate(self.btn_images):
                x = (40 + i * 95) * scale
                y = 145 * scale

                scaled_btn = pygame.transform.scale(
                    btn, (btn.get_width() * scale, btn.get_height() * scale)
                )
                screen.blit(scaled_btn, (x, y))

            for i, btn in enumerate(self.select_btn_images):
                x = (40 + i * 95) * scale
                y = 145 * scale

                scaled_btn = pygame.transform.scale(
                    btn, (btn.get_width() * scale, btn.get_height() * scale)
                )
                if self.current_selected_btn == i and not self.show_item_shit:
                    screen.blit(scaled_btn, (x, y))

            self.dialogue_box.fill((0, 0, 0))
            pygame.draw.rect(
                self.dialogue_box, (255, 255, 255), self.dialogue_box.get_rect(), 2
            )

            dialogue_scaled = pygame.transform.scale(
                self.dialogue_box,
                (
                    self.dialogue_box.get_width() * scale,
                    self.dialogue_box.get_height() * scale,
                ),
            )
            screen.blit(dialogue_scaled, (40 * scale, 84 * scale))

        else:
            self.attack_box.fill((0, 0, 0))
            attack_box_scaled = pygame.transform.scale(
                self.attack_box,
                (
                    self.attack_box.get_width() * scale,
                    self.attack_box.get_height() * scale,
                ),
            )
            pygame.draw.rect(
                attack_box_scaled, (255, 255, 255), attack_box_scaled.get_rect(), 2
            )

            where_to_put_me = (1280 / 2) - (self.attack_box.get_width() * scale) / 2
            screen.blit(attack_box_scaled, (where_to_put_me, 84 * scale))

        if self.monster_image:
            monster_scaled = pygame.transform.scale(
                self.monster_image,
                (
                    int(self.monster_image.get_width() * scale),
                    int(self.monster_image.get_height() * scale),
                ),
            )
            screen.blit(
                monster_scaled,
                (int(self.monster_x * scale), int(self.monster_y * scale)),
            )

        self.bullet_engine.draw(screen)

        if self.current_turn == self.TURN_ENEMY:
            pygame.draw.circle(
                screen, (0, 255, 0), (int(self.player_x), int(self.player_y)), 7
            )
        else:
            self.render_text_bbox = True

        self.draw_text(screen)

    def draw_text(self, screen=None):
        if screen is None:
            screen = self.screen

        # Item text gets drawn in the same dialogue box flow
        if self.item_mode:
            if self.text_engine:
                self.text_engine.draw(
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
                keys = pygame.key.get_pressed()
                if keys[pygame.K_y] and self.text_engine.finished:
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