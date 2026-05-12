import pygame
import sys
import os
import importlib
import math
from assetsLoader import Loader
from ui.textengine.textengine import TextEngine
from ThreeDee_engine.ThreeDee import ThreeDeeEngine


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
    def __init__(self, screen, true_screen):
        self.screen = screen
        self.module = None
        self.text_engine = TextEngine()
        self.threeD_engine = ThreeDeeEngine(true_screen)
        for i in range(10):
            self.threeD_engine.load_obj("bullet.obj")

        self.current_turn = 0
        self.current_selected_btn = 0

        self._prev_keys = pygame.key.get_pressed()

        # Buttons
        loader = Loader("ui/fight/fight_assets")
        self.btn_images = []

        for name in ["btn_1.png", "btn_2.png", "btn_3.png"]:
            path = loader.load(name)
            img = pygame.image.load(path).convert_alpha()
            img = img
            self.btn_images.append(img)

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

        # Teleport animation
        self.hit_timer = 0
        self.hit_duration = 0.1  # shorter, snappier
        self.hit_power = 60

        # Player
        self.player_atk = 10
        self.player_def = 5
        self.player_speed = 200
        self.player_x, self.player_y = 533,150+280
        self.speed_X, self.speed_Y = 0,0
        # Black box with white outline for dialouge
        self.dialogue_box = pygame.Surface((240, 45))
        self.dialogue_box.fill((0, 0, 0))
        self.attack_box = pygame.Surface((90, 90))
        self.attack_box.fill((0,0,0))
        self.bullets = []
        
    def load_fight(self, fight_name):
        self.module = load_fight_module(fight_name)
        if self.module:
            self.module.init(self)

        return "PPPP" #Teto won 100%, It was rigged

    def update(self, dt, joystick):
        self.move_bullet(dt)
        #print(pygame.mouse.get_pos())
        if self.module is None:
            return

        keys = pygame.key.get_pressed()

        if self.current_turn == 0:
            if keys[pygame.K_LEFT] and not self._prev_keys[pygame.K_LEFT]:
                self.current_selected_btn -= 1
            elif keys[pygame.K_RIGHT] and not self._prev_keys[pygame.K_RIGHT]:
                self.current_selected_btn += 1

            self.current_selected_btn %= len(self.btn_images)

            if keys[pygame.K_z] and not self._prev_keys[pygame.K_z]:
                if self.current_selected_btn == 0 and self.monster_hp > 0:
                    self.attack_monster()

        else:
            self.threeD_engine.update(dt, keys)

        try:
            self.module.run(self, dt, joystick)
        except Exception as e:
            print(f"[Fight] Error running fight module: {e}")



    def attack_monster(self):
        self.current_turn = 1  # Switch to monster's turn
        if self.monster_max_hp <= 0:
            return

        hp_ratio = self.monster_hp / self.monster_max_hp
        missing_hp_ratio = 1 - hp_ratio

        base = max(1, self.player_atk - self.monster_def)

        damage = max(
            1,
            (
                base
                * (1 + (self.player_atk / (self.player_atk + 100)))
                * (100 / (100 + self.monster_def))
                * (1 + missing_hp_ratio * 0.75)
                * (1 + math.sqrt(base) / 60)
            )
        )

        damage = int(damage)
        self.monster_hp -= damage
        self.monster_hp = max(0, self.monster_hp)

        print(f"Damage: {damage} | Monster HP: {self.monster_hp}")

        # Trigger teleport hit
        self.hit_timer = self.hit_duration
        self.hit_power = min(100, 20 + damage)  # monsters flies farther for big hits

    def spawn_bullet(self, x, y, size, color, damage, rotation, speed=300):
        """Spawn a bullet with direction based on rotation (degrees)."""

        rad = math.radians(rotation)

        bullet = {
            "x": x,
            "y": y,
            "vx": math.cos(rad) * speed,
            "vy": math.sin(rad) * speed,
            "size": size,
            "color": color,
            "damage": damage,
            "rotation": rotation
        }

        self.bullets.append(bullet)
    
    def move_bullet(self, dt):
        """Move all bullets and remove off-screen ones."""

        for bullet in self.bullets[:]:
            bullet["x"] += bullet["vx"] * dt
            bullet["y"] += bullet["vy"] * dt

            # Remove if off screen (adjust if needed)
            if (
                bullet["x"] < -50 or
                bullet["x"] > 1200 or
                bullet["y"] < -50 or
                bullet["y"] > 800
            ):
                self.bullets.remove(bullet)

    def draw(self, screen):
        screen.fill((0, 0, 0))
        # Draw buttons
        if self.current_turn == 0:
            for i, btn in enumerate(self.btn_images):
                x = 45 + i * 105
                y = 145
                screen.blit(btn, (x, y))
            # Draw dialogue box
            self.dialogue_box.fill((0, 0, 0))
            pygame.draw.rect(self.dialogue_box, (255, 255, 255), self.dialogue_box.get_rect(), 2)
            screen.blit(self.dialogue_box, (40, 84))
        else:
            self.text_engine.start_text("", "")
            # self.attack_box.fill((0,0,0))
            # pygame.draw.rect(self.attack_box, (255,255,255), self.attack_box.get_rect(), 2)
            # where_to_put_me = (320/2)-self.attack_box.get_width()/2
            # screen.blit(self.attack_box, (where_to_put_me, 84))
            # for bullet in self.bullets:
            #     pygame.draw.circle(
            #         screen,
            #         bullet["color"],
            #         (int(bullet["x"]), int(bullet["y"])),
            #         bullet["size"]
            #     )
            # pygame.draw.circle(screen, (0,255,0), (self.player_x, self.player_y), 7)

        # Draw monster
        if self.monster_image:
            screen.blit(self.monster_image, (self.monster_x, self.monster_y))

    def draw_text(self, screen):
            self.text_engine.draw(
                x=180,
                y=356,
                text_color=(255, 255, 255),
                choice_color=(180, 180, 180),
                highlight_color=(255, 255, 0),
                size=12,
                surface=screen
            )
            if self.current_turn == 1:
                # C++ renders offscreen, returns a Surface â€” blit it like anything else.
                # Main loop's pygame.display.flip() handles the final present. No fighting.
                surf = self.threeD_engine.draw()
                screen.blit(surf, (0, 0))
