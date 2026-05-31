import pygame
import sys
import os
import importlib
import math
from assetsLoader import Loader
from ui.textengine.textengine import TextEngine
from bulletengine.bulletengine import BulletHellEngine





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

        self.renderer = screen  # Low-res renderer (320x180 or similar)
        self.screen = true_screen  # Actual display screen (1280x720 or similar)

        self.module = None

        self.text_engine = TextEngine()

        self.running = False

        self.current_turn = 0
        
        self.current_section = 1

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


        self.select_btn_images = []
        for name in ["btn_4.png", "btn_5.png", "btn_6.png"]:

            path = loader.load(name)

            img = pygame.image.load(path).convert_alpha()

            img = img

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
        
        self.player_max_hp = 100
        self.player_hp = 100

        # Black box with white outline for dialouge

        self.dialogue_box = pygame.Surface((240, 45))

        self.dialogue_box.fill((0, 0, 0))

        self.attack_box = pygame.Surface((90, 90))

        self.attack_box.fill((0,0,0))

        # Bullet engine
        self.bullet_engine = BulletHellEngine(max_bullets=1000, fight_loader=self)

        self.text_finished_EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE = False
        self.bbox = False


    def parse_fight_text(self, text_content: str, identifier: str, section: int) -> str:
        """Parse BIG_TEXT.txt file and extract text for a specific identifier and section."""
        self.bbox = False
        section_marker_start = f"(SECTION_{section})"
        section_marker_end = f"(ENDSECTION_{section})"
        
        # Find the identifier block
        if f"{identifier} =" not in text_content:
            return ""
        
        # Find start of identifier block
        identifier_start = text_content.find(f"{identifier} =")
        if identifier_start == -1:
            return ""
        
        # Find the next identifier (or end of file)
        next_identifier_pos = len(text_content)
        remaining_text = text_content[identifier_start + len(f"{identifier} ="):]
        
        for line in remaining_text.split('\n'):
            if ' = ' in line and not line.strip().startswith('[') and not line.strip().startswith('{') and not line.strip().startswith('('):
                next_identifier_pos = identifier_start + len(f"{identifier} =") + text_content[identifier_start + len(f"{identifier} ="):].find(line)
                break
        
        identifier_block = text_content[identifier_start:next_identifier_pos]
        
        # Find the section within the identifier block
        section_start = identifier_block.find(section_marker_start)
        section_end = identifier_block.find(section_marker_end)
        
        if section_start == -1 or section_end == -1:
            return ""
        
        section_text = identifier_block[section_start + len(section_marker_start):section_end]

        if section_text.find("IN_BBOX") != -1:
            self.bbox = True
        
        # Clean up the text, removing extra whitespace and formatting markers
        lines = []
        for line in section_text.split('\n'):
            line = line.strip()
            if line and not line.startswith('[') and not line.startswith('{') and not line.startswith("IN_BBOX"):
                lines.append(line)
        
        return '\n'.join(lines)





        

    def load_fight(self, fight_name):

        self.module = load_fight_module(fight_name)

        if self.module:

            self.module.init(self)

        
        self.running = True
        print("PPPP") # Teto won 100%
        
        # Load and display initial text
        self.load_section_text()

        return self
    
    def load_section_text(self):
        """Load and display text for the current section from BIG_TEXT.txt."""
        if not hasattr(self, 'fight_identifier') or not hasattr(self, 'current_section'):
            return
        
        base_path = get_base_path()
        text_file = os.path.join(base_path, "ui", "fight", "BIG_TEXT.TXT")
        
        if not os.path.exists(text_file):
            return
        
        try:
            with open(text_file, 'r', encoding='utf-8') as f:
                text_content = f.read()
            
            section_text = self.parse_fight_text(text_content, self.fight_identifier, self.current_section)
            
            if section_text:
                self.text_engine.start_text(section_text, self.fight_identifier)
        except Exception as e:
            print(f"[Fight] Error loading section text: {e}")


    def update(self, dt, joystick=None):
        # Update bullet engine
        self.bullet_engine.update(
            dt,
            self.player_x, self.player_y, 7,  # player pos and radius
            left=-500, right=1280+500, top=-500, bottom=720+500,  # arena bounds with margin for culling
            on_hit=self.on_bullet_hit
        )

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
        
        # Player movement during monster's turn (dodging)
        if self.current_turn == 1:
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
            
            # Update player position
            self.player_x += self.speed_X * dt
            self.player_y += self.speed_Y * dt
            
            # Collision with attack box boundaries
            # Attack box: 360x360 (90 * scale), positioned at (460, 336)
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

        self.current_turn = 1  # Switch to monster's turn
        
        # Clear text when action is taken
        self.text_engine.finished = True
        self.text_finished_EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE = True

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



    def spawn_bullet(self, x, y, size, color, damage, rotation, speed=300, type="dot", angular_velocity=0.0):

        """Spawn a bullet with direction based on rotation (degrees).
        
        Uses the high-performance bullet engine instead of manual tracking.
        """

        return self.bullet_engine.spawn_at_angle(
            x=x,
            y=y,
            angle=rotation,
            speed=speed,
            size=size,
            color=color,
            bullet_type=type,
            lifetime=float('inf'),  # bullets despawn when off-screen
            angular_velocity=angular_velocity
        )



    def on_bullet_hit(self, bullet_idx):
        """Callback when a bullet hits the player."""
        # Calculate damage from monster attack
        base = max(1, self.monster_atk - self.player_def)
        damage = max(1, int(base * (1 + self.monster_atk / (self.monster_atk + 100))))
        
        self.player_hp -= damage
        self.player_hp = max(0, self.player_hp)
        
        print(f"Player hit! Damage: {damage} | Player HP: {self.player_hp}")



    def draw(self, screen=None):

        if screen is None:
            screen = self.screen
        
        # Scale factor for rendering to full-res screen instead of low-res renderer
        scale = 4

        screen.fill((0, 0, 0))

        # Draw buttons

        if self.current_turn == 0:

            for i, btn in enumerate(self.btn_images):

                x = (40 + i * 95) * scale

                y = 145 * scale

                # Scale button image
                scaled_btn = pygame.transform.scale(btn, (btn.get_width() * scale, btn.get_height() * scale))
                screen.blit(scaled_btn, (x, y))

            for i, btn in enumerate(self.select_btn_images):

                x = (40 + i * 95) * scale

                y = 145 * scale

                # Scale button image
                scaled_btn = pygame.transform.scale(btn, (btn.get_width() * scale, btn.get_height() * scale))
                if self.current_selected_btn == i:
                    screen.blit(scaled_btn, (x, y))


            # Draw dialogue box

            self.dialogue_box.fill((0, 0, 0))

            pygame.draw.rect(self.dialogue_box, (255, 255, 255), self.dialogue_box.get_rect(), 2)

            # Scale dialogue box position
            dialogue_scaled = pygame.transform.scale(self.dialogue_box, (self.dialogue_box.get_width() * scale, self.dialogue_box.get_height() * scale))
            screen.blit(dialogue_scaled, (40 * scale, 84 * scale))

        else:

            # Draw attack box
            self.attack_box.fill((0,0,0))
            attack_box_scaled = pygame.transform.scale(self.attack_box, (self.attack_box.get_width() * scale, self.attack_box.get_height() * scale))
            pygame.draw.rect(attack_box_scaled, (255,255,255), attack_box_scaled.get_rect(), 2)

            where_to_put_me = (1280/2) - (self.attack_box.get_width() * scale)/2
            screen.blit(attack_box_scaled, (where_to_put_me, 84 * scale))



        # Draw monster

        if self.monster_image:
            # Scale monster position and size
            monster_scaled = pygame.transform.scale(self.monster_image, (int(self.monster_image.get_width() * scale), int(self.monster_image.get_height() * scale)))
            screen.blit(monster_scaled, (int(self.monster_x * scale), int(self.monster_y * scale)))

        # Draw bullets using the bullet engine

        self.bullet_engine.draw(screen)
        
        # Draw player circle only during monster's turn
        if self.current_turn == 1:
            pygame.draw.circle(screen, (0, 255, 0), (int(self.player_x), int(self.player_y)), 7)
        
        # Draw text engine
        self.draw_text(screen)



    def draw_text(self, screen=None):

            if screen is None:
                screen = self.screen
            
            # Only draw text during player's turn (not during enemy's turn)
            if self.bbox:
                # IN_BBOX aanwezig: render normaal tijdens spelers beurt
                if self.current_turn == 0:
                    self.text_engine.draw(
                        x=180,
                        y=356,
                        text_color=(255, 255, 255),
                        choice_color=(180, 180, 180),
                        highlight_color=(255, 255, 0),
                        size=12,
                        surface=screen
                    )
            else:
                # Geen IN_BBOX: render tijdens enemy beurt
                if self.current_turn == 1:
                    self.text_engine.draw(
                        x=280,
                        y=200,
                        text_color=(255, 255, 255),
                        choice_color=(180, 180, 180),
                        highlight_color=(255, 255, 0),
                        size=12,
                        surface=screen
                    )