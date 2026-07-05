import os
import re
import random
import math
import json
import locale

import pygame
from googletrans import Translator

from assetsLoader import Loader

# Sentinel character used as a placeholder in parsed_text for inline images.
# Must never appear in real dialogue strings.
IMAGE_PLACEHOLDER = "\x01"


class TextEngine:
    def __init__(self, font="PixelFont.ttf"):
        # Load font
        font_loader = Loader("ui/textengine")
        self.font_path = font_loader.load(font)
        self.font = pygame.font.Font(self.font_path, 24)
        self.txt_path = font_loader.load("all_text.json")

        # Typing
        self.text = ""
        self.parsed_text = ""
        self.char_effects = {}  # index -> list of effects
        self.char_index = 0
        self.base_speed = 20  # chars/sec
        self.timer = 0.0
        self.finished = False
        self.wait_ms = 0.0

        # Sound
        self.type_sound = None
        self.play_sound_interval = 2
        self.last_sound_char = 0

        # Choices
        self.choices = []
        self.selected_choice = 0
        self.showing_choices = False
        self.pressed_last_frame = False
        self.just_opened_choices = False

        # Visual
        self.current_color = (255, 255, 255)
        self.shake_intensity = 0
        self.time = 0.0

        # Roar clones (global system, independent of char_index)
        self.roar_clones = []
        self.ROAR_CLONE_SPEED = 120.0
        self.ROAR_CLONE_FADE = 260.0
        self.ROAR_CLONE_MAX_TRAVEL = 200.0
        self.ROAR_CLONE_SPAWN_INTERVAL = 0.15
        self.ROAR_CLONE_MAX_PER_CHAR = 20
        self.ROAR_CLONE_INITIAL_ALPHA = 180
        self.roar_global_timer = 0.0

        # Glyph cache: (char, color, font_size, outline_width) -> (surface, width)
        self.glyph_cache = {}
        self.last_font_size = 24

        # Text block surface cache for static (non-animated) text
        self._text_surf_cache = None
        self._text_surf_cache_key = None

        # Image support
        self.image_cache = {}

        print(locale.getdefaultlocale())

    # -----------------------------
    # Parse tags
    # -----------------------------
    def parse_effects(self, text):
        parsed = ""
        char_effects = {}

        # Added image\([^)]+\) to recognise ^image(filename) tags.
        pattern = r"\^(shake\d+|speed\d+|color\(\d+,\d+,\d+\)|sp\d+|wait\d+|special|endspecial|roar|endroar|image\([^)]+\))"

        index = 0
        in_block = False
        block_type = None
        block_effects = []
        block_start = 0

        for match in re.finditer(pattern, text):
            start, end = match.span()
            tag = match.group()[1:]

            for c in text[index:start]:
                char_effects.setdefault(len(parsed), [])
                parsed += c

            if tag == "special":
                in_block = True
                block_type = "special"
                block_start = len(parsed)
                block_effects = []
            elif tag == "endspecial":
                if in_block and block_type == "special":
                    for i in range(block_start, len(parsed)):
                        char_effects.setdefault(i, []).extend(block_effects)
                in_block = False
                block_type = None
            elif tag == "roar":
                in_block = True
                block_type = "roar"
                block_start = len(parsed)
                block_effects = ["roar"]
            elif tag == "endroar":
                if in_block and block_type == "roar":
                    for i in range(block_start, len(parsed)):
                        char_effects.setdefault(i, []).extend(block_effects)
                in_block = False
                block_type = None
            elif tag == "freedom":
                in_block = True
                block_type = "freedom"
                block_start = len(parsed)
                block_effects = ["freedom"]
            elif tag == "locked":
                if in_block and block_type == "freedom":
                    for i in range(block_start, len(parsed)):
                        char_effects.setdefault(i, []).extend(block_effects)
                in_block = False
                block_type = None
            else:
                if in_block and block_type == "special":
                    block_effects.append(tag)
                else:
                    # Image tags insert a placeholder character.
                    if tag.startswith("image(") and tag.endswith(")"):
                        char_effects.setdefault(len(parsed), []).append(tag)
                        parsed += IMAGE_PLACEHOLDER
                    else:
                        char_effects.setdefault(len(parsed), []).append(tag)

            index = end

        for c in text[index:]:
            char_effects.setdefault(len(parsed), [])
            parsed += c

        return parsed, char_effects

    # -----------------------------
    # Start text / choices
    # -----------------------------
    def start_text(self, text, origin="ui"):
        self.parsed_text, self.char_effects = self.parse_effects(text)
        self.text = text
        self.char_index = 0
        self.timer = 0.0
        self.finished = False
        self.wait_ms = 0.0
        self.choices = []
        self.showing_choices = False
        self.just_opened_choices = False
        self.pressed_last_frame = False
        self.current_color = (255, 255, 255)
        self.shake_intensity = 0
        self.time = 0.0
        self.roar_clones = []
        self.roar_global_timer = 0.0
        self.last_sound_char = 0
        self._text_surf_cache = None
        self._text_surf_cache_key = None

        # Load typing sound
        sound_loader = Loader("sprites/")
        sound_path = sound_loader.load(f"{origin}/type.wav")
        if os.path.exists(sound_path):
            try:
                self.type_sound = pygame.mixer.Sound(sound_path)
            except Exception:
                self.type_sound = None
        else:
            self.type_sound = None

        # If there is no text, finish immediately so choice menus can render on frame 1.
        if not self.parsed_text:
            self.finished = True

    async def translate_shit(self, input):
        async with Translator() as translator:
            result = await translator.translate(input, dest="en")
            return result

    def start_choices(self, text, choices, origin="ui"):
        self.start_text(text, origin)
        self.choices = choices
        self.selected_choice = 0
        self.showing_choices = True

        # Make choice menus appear immediately when there is no typed text.
        if not self.parsed_text:
            self.finished = True
            self.char_index = 0

        # Eat the opening press so the same confirm button doesn't instantly select/close.
        self.pressed_last_frame = True
        self.just_opened_choices = True

    # -----------------------------
    # Visual effects
    # -----------------------------
    def apply_effect(self, effect):
        if effect.startswith("shake"):
            try:
                self.shake_intensity = int(effect[5:])
            except Exception:
                self.shake_intensity = 0
        elif effect.startswith("color"):
            try:
                nums = effect[6:-1].split(",")
                r, g, b = map(int, nums)
                self.current_color = (r, g, b)
            except Exception:
                self.current_color = (255, 255, 255)
        elif effect.startswith("sp"):
            try:
                sp = int(effect[2:])
                if sp == 1:
                    self.shake_intensity = 8
                elif sp == 2:
                    self.current_color = (
                        random.randint(0, 255),
                        random.randint(0, 255),
                        random.randint(0, 255),
                    )
                elif sp == 3:
                    self.current_color = (200, 200, 255)
            except Exception:
                pass

    def reset_effects(self):
        self.current_color = (255, 255, 255)
        self.shake_intensity = 0

    # -----------------------------
    # Update (typing + clones)
    # -----------------------------
    def update(self, dt):
        self.time += dt

        # Update existing clones
        for clone in self.roar_clones[:]:
            clone["x"] += self.ROAR_CLONE_SPEED * dt
            clone["alpha"] -= self.ROAR_CLONE_FADE * dt
            if clone["alpha"] <= 0 or abs(clone["x"] - clone["origin_x"]) > self.ROAR_CLONE_MAX_TRAVEL:
                self.roar_clones.remove(clone)

        # Spawn new roar clones at wavy y
        self.roar_global_timer -= dt
        while self.roar_global_timer <= 0:
            positions = self._compute_char_positions()

            # Compute word indices for waves (like in draw)
            word_index_map = {}
            idx = 0
            for line in self.parsed_text.split("&"):
                word_idx = -1
                prev_space = True
                for ch in line:
                    if prev_space and ch != " ":
                        word_idx += 1
                        prev_space = False
                    if ch == " ":
                        prev_space = True
                    word_index_map[idx] = word_idx
                    idx += 1
                idx += 1  # newline index

            for i in range(min(self.char_index, len(self.parsed_text))):
                if "roar" not in self.char_effects.get(i, []):
                    continue
                ch = self.parsed_text[i]
                if ch == " " or ch == IMAGE_PLACEHOLDER:
                    continue

                count_existing = sum(1 for c in self.roar_clones if c["origin_idx"] == i)
                if count_existing >= self.ROAR_CLONE_MAX_PER_CHAR:
                    continue

                ox, oy = positions[i]
                word_idx = word_index_map.get(i, 0)
                wave = int(math.sin(self.time * 4 + word_idx * 0.6) * 6)
                ry = oy + wave + random.uniform(-1, 1)
                rx = ox + random.uniform(-2, 2)
                color = self._get_char_color(i)

                self.roar_clones.append(
                    {
                        "x": rx,
                        "y": ry,
                        "alpha": float(self.ROAR_CLONE_INITIAL_ALPHA),
                        "origin_idx": i,
                        "origin_x": rx,
                        "char": ch,
                        "color": color,
                    }
                )

            self.roar_global_timer += self.ROAR_CLONE_SPAWN_INTERVAL

        # Typing logic
        if self.finished:
            return

        if self.wait_ms > 0:
            self.wait_ms -= dt * 1000
            if self.wait_ms > 0:
                return
            self.wait_ms = 0

        self.timer += dt
        while self.char_index < len(self.parsed_text):
            effects = self.char_effects.get(self.char_index, [])
            time_per_char = 1.0 / self.base_speed
            wait_for = None

            for eff in effects:
                if eff.startswith("wait"):
                    wait_for = int(eff[4:])
                elif eff.startswith("speed"):
                    sp = int(eff[5:])
                    if sp > 0:
                        time_per_char = 1.0 / sp

            if wait_for:
                self.wait_ms = wait_for
                self.char_effects[self.char_index] = [e for e in effects if not e.startswith("wait")]
                break

            if self.timer < time_per_char:
                break

            self.timer -= time_per_char
            self.char_index += 1

            # Play typing sound – skip for image placeholders.
            if self.type_sound and self.play_sound_interval > 0:
                if self.char_index - self.last_sound_char >= self.play_sound_interval:
                    last_ch = self.parsed_text[self.char_index - 1]
                    if last_ch != " " and last_ch != IMAGE_PLACEHOLDER:
                        try:
                            self.type_sound.play()
                        except Exception:
                            pass
                    self.last_sound_char = self.char_index

        if self.char_index >= len(self.parsed_text):
            self.finished = True

    # -----------------------------
    # Helper: compute character positions
    # -----------------------------
    def _compute_char_positions(self):
        positions = {}
        lines = self.parsed_text.split("&")
        idx = 0
        y = 0
        for line in lines:
            x = 0
            for ch in line:
                positions[idx] = (x, y)
                if ch == IMAGE_PLACEHOLDER:
                    img = self._image_from_effects(self.char_effects.get(idx, []))
                    w = img.get_width() if img else 0
                else:
                    w, _ = self.font.size(ch)
                x += w
                idx += 1
            idx += 1
            y += self.font.get_height()
        return positions

    def _get_char_color(self, idx):
        effects = self.char_effects.get(idx, [])
        for eff in effects:
            if eff.startswith("color"):
                try:
                    nums = eff[6:-1].split(",")
                    r, g, b = map(int, nums)
                    return (r, g, b)
                except Exception:
                    pass
        return (255, 255, 255)

    # -----------------------------
    # Image support
    # -----------------------------
    def _image_from_effects(self, effects):
        for eff in effects:
            if eff.startswith("image(") and eff.endswith(")"):
                return self._load_image(eff[6:-1])
        return None

    def _load_image(self, image_name):
        if image_name in self.image_cache:
            return self.image_cache[image_name]

        try:
            loader = Loader("ui/textengine/txt_images")
            path = loader.load(image_name)
            img = pygame.image.load(path).convert_alpha()
            self.image_cache[image_name] = img
            return img
        except Exception as e:
            print(f"[TextEngine] Could not load image '{image_name}': {e}")
            self.image_cache[image_name] = None
            return None

    def _render_glyph_with_outline(self, char, text_color, outline_color, outline_width, size):
        cache_key = (char, text_color, outline_color, outline_width, size)
        if cache_key in self.glyph_cache:
            return self.glyph_cache[cache_key]

        padding = outline_width + 2
        char_surf = self.font.render(char, True, text_color)
        width = char_surf.get_width() + 2 * padding
        height = char_surf.get_height() + 2 * padding
        result_surf = pygame.Surface((width, height), pygame.SRCALPHA)

        outline_surf = self.font.render(char, True, outline_color)
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx != 0 or dy != 0:
                    result_surf.blit(outline_surf, (padding + dx, padding + dy))

        result_surf.blit(char_surf, (padding, padding))
        cached = (result_surf, -padding, -padding, char_surf.get_width())
        self.glyph_cache[cache_key] = cached
        return cached

    def load(self, text_name):
        with open(self.txt_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data[text_name]

    # -----------------------------
    # Draw with outline for all text
    # -----------------------------
    def draw(
        self,
        x,
        y,
        text_color=(255, 255, 255),
        outline_color=(0, 0, 0),
        choice_color=(180, 180, 180),
        highlight_color=(255, 255, 0),
        outline_width=1,
        size=24,
        surface=None,
    ):
        if surface is None:
            surf = pygame.display.get_surface()
        else:
            surf = surface

        if surf is None:
            print("[TextEngine.draw] WARNING: surf is None!")
            return

        # update font size if needed, clear caches on change
        if self.font.get_height() != size:
            self.font = pygame.font.Font(self.font_path, size)
            if self.last_font_size != size:
                self.glyph_cache.clear()
                self.last_font_size = size

        if len(self.glyph_cache) > 2000:
            self.glyph_cache.clear()

        # roar clones first
        for clone in self.roar_clones:
            a = max(0, int(clone["alpha"]))
            if a <= 0:
                continue
            glyph = self.font.render(clone["char"], True, clone["color"])
            try:
                glyph.set_alpha(a)
            except Exception:
                pass
            surf.blit(glyph, (x + clone["x"], y + clone["y"]))

        # main text
        visible = self.parsed_text[: self.char_index]
        lines = visible.split("&")

        # Check if any visible char has animated effects
        has_animated = any(
            any(e.startswith("shake") or e == "roar" or e.startswith("sp") for e in self.char_effects.get(i, []))
            for i in range(self.char_index)
        )

        cache_key = (self.char_index, text_color, outline_color, outline_width, size)

        if not has_animated and self._text_surf_cache_key == cache_key and self._text_surf_cache is not None:
            surf.blit(self._text_surf_cache, (x, y))
        else:
            line_height = self.font.get_height()

            # Build cache surface dimensions
            if not has_animated:
                total_width = 1
                max_img_h = line_height
                scan_idx = 0
                for line in lines:
                    line_w = 0
                    for ch in line:
                        if ch == IMAGE_PLACEHOLDER:
                            img = self._image_from_effects(self.char_effects.get(scan_idx, []))
                            if img:
                                line_w += img.get_width()
                                max_img_h = max(max_img_h, img.get_height())
                        else:
                            line_w += self._render_glyph_with_outline(
                                ch, text_color, outline_color, outline_width, size
                            )[3]
                        scan_idx += 1
                    scan_idx += 1
                    total_width = max(total_width, line_w + (outline_width + 2) * 2)

                total_height = max((len(lines) - 1) * line_height + max_img_h, 1)
                cache_surf = pygame.Surface((total_width, total_height), pygame.SRCALPHA)

            idx = 0
            rel_y = 0

            for line in lines:
                rel_x = 0
                word_index = -1
                prev_space = True

                for ch in line:
                    self.current_color = text_color
                    self.shake_intensity = 0

                    effects = self.char_effects.get(idx, [])
                    for eff in effects:
                        self.apply_effect(eff)

                    if prev_space and ch != " ":
                        word_index += 1
                        prev_space = False
                    if ch == " ":
                        prev_space = True

                    if ch == IMAGE_PLACEHOLDER:
                        img = self._image_from_effects(effects)
                        if img:
                            if has_animated:
                                shake_x = random.randint(-self.shake_intensity, self.shake_intensity) if self.shake_intensity else 0
                                shake_y = random.randint(-self.shake_intensity, self.shake_intensity) if self.shake_intensity else 0
                                wave = int(math.sin(self.time * 4 + word_index * 0.6) * 6) if "roar" in effects else 0
                                surf.blit(img, (x + rel_x + shake_x, y + rel_y + wave + shake_y))
                            else:
                                cache_surf.blit(img, (rel_x, rel_y))
                            rel_x += img.get_width()
                        idx += 1
                        continue

                    cached_glyph, offset_x_adj, offset_y_adj, char_width = self._render_glyph_with_outline(
                        ch, self.current_color, outline_color, outline_width, size
                    )

                    if has_animated:
                        shake_x = random.randint(-self.shake_intensity, self.shake_intensity) if self.shake_intensity else 0
                        shake_y = random.randint(-self.shake_intensity, self.shake_intensity) if self.shake_intensity else 0
                        wave = int(math.sin(self.time * 4 + word_index * 0.6) * 6) if "roar" in effects else 0
                        surf.blit(
                            cached_glyph,
                            (x + rel_x + offset_x_adj + shake_x, y + rel_y + offset_y_adj + wave + shake_y),
                        )
                    else:
                        cache_surf.blit(cached_glyph, (rel_x + offset_x_adj, rel_y + offset_y_adj))

                    rel_x += char_width
                    idx += 1

                rel_y += line_height
                idx += 1

            if not has_animated:
                self._text_surf_cache = cache_surf
                self._text_surf_cache_key = cache_key
                surf.blit(cache_surf, (x, y))

        # choices
        if self.showing_choices and self.finished:
            choices_y = y + len(lines) * self.font.get_height() + 10
            for i, c in enumerate(self.choices):
                col = highlight_color if i == self.selected_choice else choice_color
                prefix = "> " if i == self.selected_choice else "  "
                line_surf = self.font.render(prefix + c, True, col)
                surf.blit(line_surf, (x, choices_y))
                choices_y += line_surf.get_height()

    # -----------------------------
    # Handle choices
    # -----------------------------
    def handle_choice_input(self, keys, joystick):
        # Let the first frame after opening settle.
        if self.just_opened_choices:
            self.just_opened_choices = False
            return None

        if not self.showing_choices or not self.finished:
            return None

        action_up = False
        action_down = False
        action_confirm = False

        # Keyboard and joystick
        if keys is not None:
            if keys[pygame.K_UP]:
                action_up = True
            if keys[pygame.K_DOWN]:
                action_down = True
            if keys[pygame.K_z]:
                action_confirm = True

        if joystick:
            try:
                hat = joystick.get_hat(0)
                if hat[1] == 1 or joystick.get_axis(1) < -0.5:
                    action_up = True
                if hat[1] == -1 or joystick.get_axis(1) > 0.5:
                    action_down = True
                if joystick.get_button(1):
                    action_confirm = True
            except Exception:
                pass

        # Input handling (anti-hold)
        if not self.pressed_last_frame:
            if action_up:
                self.selected_choice = (self.selected_choice - 1) % len(self.choices)
                self.pressed_last_frame = True
            elif action_down:
                self.selected_choice = (self.selected_choice + 1) % len(self.choices)
                self.pressed_last_frame = True
            elif action_confirm:
                self.pressed_last_frame = True
                chosen = self.choices[self.selected_choice]
                self.showing_choices = False
                self.just_opened_choices = False
                return chosen
        else:
            if not (action_up or action_down or action_confirm):
                self.pressed_last_frame = False

        return None
