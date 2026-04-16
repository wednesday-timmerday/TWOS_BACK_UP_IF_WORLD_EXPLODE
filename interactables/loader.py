import pygame
import importlib.util
import os
import sys

from ui.textengine.textengine import TextEngine
from sprites.save.save import SaveOBJ


def get_base_path():
    if hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(".")


def load_cutscene_module(cutscene_id: str):
    base_path = get_base_path()
    cutscene_path = os.path.join(base_path, "interactables", f"{cutscene_id}.py")

    if not os.path.exists(cutscene_path):
        print(f"[CutsceneLoader] Missing cutscene file: {cutscene_path}")
        return None

    module_name = f"cutscene_{cutscene_id}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, cutscene_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as e:
        print(f"[CutsceneLoader] Failed to load cutscene {cutscene_id}: {e}")
        return None

    if not hasattr(module, "run") and not hasattr(module, "Interactable"):
        print(f"[CutsceneLoader] Missing 'run()' or 'Interactable' class in {cutscene_id}.py")
        return None

    return module


class Interactable:
    def __init__(self):
        self.saveOBJ = SaveOBJ()
        self.text_engine = TextEngine()

        self.running = False
        self.waiting_to_start = False
        self.player_locked = False
        self.old = False

        self.module = None
        self.world = None
        self.player = None
        self.joystick = None
        self.event = None

        # input state
        self.prev_z = False
        self.prev_x = False
        self.z_just_pressed = False
        self.x_just_pressed = False

        # dialogue state
        self.trigger_idx = None
        self.line_index = 0
        self.talking = ""

        # text settings
        self.text_skippable = True
        self.text_auto_forward = 0.0
        self.text_auto_timer = 0.0

        # running function hook
        self.running_function = None

        # choice state
        self.waiting_for_choice = False
        self.pending_choice_label = None
        self.selected_choice = None

    # ---------------------------------------------------------

    def _norm(self, s: str) -> str:
        return " ".join(s.strip().split()).casefold()

    def load_dialogue(self, filename):
        base = get_base_path()
        filename_true = os.path.join(base, "interactables", filename)
        dialogue = {}
        current_key = None

        with open(filename_true, "r", encoding="utf-8") as file:
            for raw_line in file:
                line = raw_line.strip()
                if not line:
                    continue
                if line.endswith("="):
                    current_key = line[:-1].strip()
                    dialogue[current_key] = []
                    continue
                if current_key:
                    dialogue[current_key].append(line)

        return dialogue

    # ---------------------------------------------------------

    def load(self, cutscene_id: str, joystick, trigger_idx=None):
        self.old = False
        raw_module = load_cutscene_module(cutscene_id)

        if not raw_module:
            self.running = False
            self.waiting_to_start = False
            return

        if hasattr(raw_module, "Interactable"):
            try:
                self.module = raw_module.Interactable(self.player, self.world, self)
                self.old = False
            except Exception as e:
                print(f"[CutsceneLoader] Failed to instantiate cutscene class: {e}")
                self.running = False
                self.waiting_to_start = False
                return
        else:
            self.module = raw_module
            self.old = True

        # wait for Z before starting
        self.running = False
        self.waiting_to_start = True
        self.player_locked = False

        self.joystick = joystick
        self.trigger_idx = trigger_idx
        self.running_function = None
        self.waiting_for_choice = False
        self.pending_choice_label = None
        self.selected_choice = None

        self.prev_z = False
        self.prev_x = False
        self.z_just_pressed = False
        self.x_just_pressed = False

        if not self.old:
            all_dialogue = self.load_dialogue("BIG_TEXT.txt")
            self.module.text = all_dialogue.get(self.module.dialogue_id, [])

        self.text_engine.text = ""
        self.text_engine.char_index = 0
        self.text_engine.finished = False
        self.line_index = 0

        self.text_skippable = True
        self.text_auto_forward = 0.0
        self.text_auto_timer = 0.0

    # ---------------------------------------------------------

    def _find_choice_line(self, label):
        target = self._norm(label)
        for i, line in enumerate(self.module.text):
            if line.startswith("(CHOICE)"):
                parts = line[len("(CHOICE)"):].strip().split(";")
                if parts and self._norm(parts[0]) == target:
                    return i
        return None

    def _find_branch_line(self, label, start_index=0):
        target = self._norm(label)
        for i in range(start_index, len(self.module.text)):
            line = self.module.text[i]
            if line.startswith("(BRANCH)"):
                branch_label = line[len("(BRANCH)"):].strip()
                if self._norm(branch_label) == target:
                    return i
        return None

    def _skip_block_from_branch(self, branch_index):
        if branch_index >= len(self.module.text):
            return branch_index
        if not self.module.text[branch_index].startswith("(BRANCH)"):
            return branch_index

        depth = 1
        i = branch_index + 1

        while i < len(self.module.text):
            line = self.module.text[i]
            if line.startswith("(BRANCH)") or line.startswith("(CHOICE)"):
                depth += 1
            elif line == "(ENDBRANCH)":
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1

        return i

    def _skip_remaining_sibling_branches(self):
        while self.line_index < len(self.module.text):
            next_line = self.module.text[self.line_index]
            if next_line.startswith("(BRANCH)"):
                self.line_index = self._skip_block_from_branch(self.line_index)
            else:
                break

    # ---------------------------------------------------------

    def _advance_dialogue(self):
        self.player.can_move = False

        while self.line_index < len(self.module.text):
            line = self.module.text[self.line_index]

            # [Speaker]
            if line.startswith("[") and line.endswith("]"):
                self.talking = line[1:-1].strip()
                if self.talking == "":
                    self.talking = "zund"
                self.line_index += 1
                continue

            # {(skippable auto_forward)}
            elif line.startswith("{("):
                inside = line[2:-2].strip()
                parts = inside.split()
                self.text_skippable = parts[0] == "1"
                self.text_auto_forward = float(parts[1])
                self.text_auto_timer = 0.0
                self.line_index += 1
                continue

            # ({inline text})
            elif line.startswith("({"):
                text = line[2:-2].replace("CHARA_NAME", self.player.chara_name)
                self.text_engine.start_text(text, "")
                self.line_index += 1
                return

            # ENDOFCONVERSATION
            elif line == "ENDOFCONVERSATION":
                self.line_index += 1
                self.running = False
                self.player.can_move = True
                return

            # (ENDBRANCH)
            elif line == "(ENDBRANCH)":
                self.line_index += 1
                self._skip_remaining_sibling_branches()
                continue

            # (REROUTE) label
            elif line.startswith("(REROUTE)"):
                label = line[len("(REROUTE)"):].strip()
                target = self._find_choice_line(label)
                if target is None:
                    print(f"[CutsceneLoader] REROUTE target not found: {label}")
                    self.line_index += 1
                    continue
                self.line_index = target
                self.waiting_for_choice = False
                self.pending_choice_label = None
                self.selected_choice = None
                continue

            # (CHOICE) question; option1; option2; ...
            elif line.startswith("(CHOICE)"):
                parts = line[len("(CHOICE)"):].strip().split(";")
                question = parts[0].strip()
                options = [o.strip() for o in parts[1:]]
                self.pending_choice_label = question
                self.line_index += 1
                self.waiting_for_choice = True
                self.text_engine.start_choices(question, options)
                return

            # (BRANCH) label — unexpected, skip whole block
            elif line.startswith("(BRANCH)"):
                self.line_index = self._skip_block_from_branch(self.line_index)
                continue

            # {func_name}
            elif line.startswith("{") and line.endswith("}"):
                func_name = line[1:-1].strip()
                if hasattr(self.module, func_name) and callable(getattr(self.module, func_name)):
                    self.running_function = func_name
                    self.line_index += 1
                    return
                else:
                    print(f"[CutsceneLoader] Unknown function: {func_name}")
                    self.line_index += 1
                    continue

            # regular dialogue line
            else:
                break

        if self.line_index >= len(self.module.text):
            self.running = False
            self.player.can_move = True
            return

        real_line = self.module.text[self.line_index].replace("CHARA_NAME", self.player.name)
        self.text_engine.start_text(real_line, self.talking)
        self.line_index += 1

    # ---------------------------------------------------------

    def _handle_choice_made(self, chosen_option):
        self.waiting_for_choice = False
        self.selected_choice = chosen_option

        branch_index = self._find_branch_line(chosen_option, start_index=self.line_index)
        if branch_index is None:
            print(f"[CutsceneLoader] No branch found for choice: {chosen_option}")
            self._advance_dialogue()
            return

        self.line_index = branch_index + 1
        self._advance_dialogue()

    # ---------------------------------------------------------

    def update(self, dt):
        if not self.module:
            return

        keys = pygame.key.get_pressed()
        z_pressed = keys[pygame.K_z] or keys[pygame.K_y]
        x_pressed = keys[pygame.K_x]

        self.z_just_pressed = z_pressed and not self.prev_z
        self.x_just_pressed = x_pressed and not self.prev_x

        # waiting for the player to press Z before anything starts
        if self.waiting_to_start:
            if self.z_just_pressed:
                self.player.curr_animation = "Idle"
                self.player.curr_frame = 0
                self.waiting_to_start = False
                self.running = True
                self.player_locked = True

                if not self.old:
                    self._advance_dialogue()

            self.prev_z = z_pressed
            self.prev_x = x_pressed
            return

        self.prev_z = z_pressed
        self.prev_x = x_pressed

        if not self.running:
            return

        try:
            if not self.old:
                self.module.dt = dt

                # --- function hook ---
                if self.running_function:
                    if not self.text_engine.text or self.z_just_pressed:
                        func = getattr(self.module, self.running_function)
                        result = func()
                        if result == "YES":
                            self.running_function = None
                            self._advance_dialogue()
                    return

                # --- choice input ---
                if self.waiting_for_choice:
                    self.text_engine.update(dt)
                    if self.text_engine.showing_choices and self.text_engine.finished:
                        chosen = self.text_engine.handle_choice_input(keys)
                        if chosen:
                            self._handle_choice_made(chosen)
                    return

                # --- text scrolling ---
                if not self.text_engine.finished:
                    self.text_engine.update(dt)
                    if self.text_skippable and self.x_just_pressed:
                        self.text_engine.char_index = len(self.text_engine.text)
                        self.text_engine.finished = True

                # --- text finished, waiting to advance ---
                else:
                    if self.text_auto_forward > 0:
                        self.text_auto_timer += dt
                        if self.text_auto_timer >= self.text_auto_forward:
                            self.text_auto_timer = 0.0
                            self._advance_dialogue()
                    else:
                        if self.z_just_pressed or (self.joystick and self.joystick.get_button(0)):
                            self._advance_dialogue()

            else:
                self.module.run(
                    self, dt, self.player, self.world, self.joystick, self.event
                )

        except Exception as e:
            print(f"[CutsceneLoader] Error in cutscene: {e}")
            import traceback
            traceback.print_exc()
            self.running = False
            self.waiting_to_start = False
            self.player_locked = False

        if not self.running:
            self.player_locked = False
    # ---------------------------------------------------------

    def draw(self, surface):
        if self.waiting_to_start:
            font = pygame.font.SysFont(None, 24)
            txt = font.render("Press Z", True, (255, 255, 255))
            surface.blit(txt, (50, 50))

        if self.text_engine.text:
            self.text_engine.draw(
                x=50,
                y=50,
                text_color=(255, 255, 255),
                choice_color=(180, 180, 180),
                highlight_color=(255, 255, 0)
            )

        if self.module and hasattr(self.module, "draw"):
            try:
                self.module.draw(self, surface)
            except Exception as e:
                print(f"[CutsceneLoader] Error in cutscene draw: {e}")