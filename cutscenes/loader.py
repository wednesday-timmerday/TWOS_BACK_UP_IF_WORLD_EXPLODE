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
    cutscene_path = os.path.join(base_path, "cutscenes", f"{cutscene_id}.py")

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

    if not hasattr(module, "run") and not hasattr(module, "cutscene"):
        print(f"[CutsceneLoader] Missing 'run()' or 'cutscene' class in {cutscene_id}.py")
        return None

    return module


class CutsceneLoader:
    def __init__(self):
        self.saveOBJ = SaveOBJ()
        self.text_engine = TextEngine()

        self.running = False
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

        # text position
        self.text_x = 50
        self.text_y = 50

        # running function hook
        self.running_function = None

        # choice state
        self.waiting_for_choice = False
        self.pending_choice_label = None
        self.selected_choice = None
        self.add_idx = True

    # ---------------------------------------------------------

    def _norm(self, s: str) -> str:
        return " ".join(s.strip().split()).casefold()

    def load_dialogue(self, filename):
        base = get_base_path()
        filename_true = os.path.join(base, "cutscenes", filename)
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
            return

        if hasattr(raw_module, "cutscene"):
            try:
                self.module = raw_module.cutscene(self.player, self.world, self)
                self.old = False
            except Exception as e:
                print(f"[CutsceneLoader] Failed to instantiate cutscene class: {e}")
                self.running = False
                return
        else:
            self.module = raw_module
            self.old = True

        self.running = True
        self.player_locked = True
        self.player.can_move = False
        self.joystick = joystick
        self.trigger_idx = trigger_idx
        self.running_function = None
        self.waiting_for_choice = False
        self.pending_choice_label = None
        self.selected_choice = None

        if not self.old:
            all_dialogue = self.load_dialogue("BIG_TEXT.txt")
            self.module.text = all_dialogue.get(self.module.dialogue_id, [])

            # Parse (POS x y) header lines
            self.text_x = 50
            self.text_y = 50
            filtered = []
            for line in self.module.text:
                if line.startswith("(POS)"):
                    parts = line[5:].strip().split()
                    if len(parts) >= 2:
                        try:
                            self.text_x = int(parts[0])
                            self.text_y = int(parts[1])
                        except ValueError:
                            pass
                else:
                    filtered.append(line)
            self.module.text = filtered

        self.text_engine.text = ""
        self.text_engine.char_index = 0
        self.text_engine.finished = False
        self.line_index = 0

        self.text_skippable = True
        self.text_auto_forward = 0.0
        self.text_auto_timer = 0.0

        if not self.old:
            self._advance_dialogue()

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
        """
        Skip from a (BRANCH) line to just after its matching (ENDBRANCH).
        Handles nested (BRANCH), (CHOICE), and (ENDBRANCH) pairs safely.
        Returns the index after the matching ENDBRANCH.
        """
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
        """
        After one branch finishes, skip any following sibling branches
        until the next non-branch line.
        """
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

            # (BRANCH) label
            elif line.startswith("(BRANCH)"):
                # If we landed here unexpectedly, skip this whole block.
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

            elif line == "ENDOFCONVERSATION":
                self.line_index += 1
                self.running = False
                self.player.can_move = True
                self.player.incutscene = False
                return

            elif line == "DONTADDIDX":
                self.line_index += 1
                self.add_idx = False
                continue


            # regular dialogue line
            else:
                break

        if self.line_index >= len(self.module.text):
            self.running = False
            self.player.can_move = True
            return

        real_line = self.module.text[self.line_index].replace("CHARA_NAME", self.player.name)
        real_line = real_line.replace("NAME", self.player.true_name)
        self.text_engine.start_text(real_line, self.talking)
        self.line_index += 1

    # ---------------------------------------------------------

    def _handle_choice_made(self, chosen_option):
        """
        Jump into the matching branch body for the chosen option.
        """
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

    def update(self, dt, player):
        if not self.running:
            self.player_locked = False
            if self.add_idx:
                self.player._triggered_once.add(self.trigger_idx)
            return

        # Keep cutscene 2 locked
        if hasattr(self.module, "dialogue_id") and self.module.dialogue_id == "2":
            self.player.can_move = False

        if not self.module:
            return

        keys = pygame.key.get_pressed()
        z_pressed = keys[pygame.K_z] or keys[pygame.K_y] or (self.joystick and self.joystick.get_button(1))
        x_pressed = keys[pygame.K_x] or (self.joystick and self.joystick.get_button(0))

        self.z_just_pressed = z_pressed and not self.prev_z
        self.x_just_pressed = x_pressed and not self.prev_x
        self.prev_z = z_pressed
        self.prev_x = x_pressed

        try:
            if not self.old:
                self.module.dt = dt

                if self.running_function:
                    func = getattr(self.module, self.running_function)
                    result = func()

                    if result == "YES":
                        self.running_function = None
                        self._advance_dialogue()
                    return

                if self.waiting_for_choice:
                    self.text_engine.update(dt)
                    if self.text_engine.showing_choices and self.text_engine.finished:
                        chosen = self.text_engine.handle_choice_input(keys, self.joystick)
                        if chosen:
                            self._handle_choice_made(chosen)
                    return

                if not self.text_engine.finished:
                    self.text_engine.update(dt)
                    if self.text_skippable and self.x_just_pressed:
                        self.text_engine.char_index = len(self.text_engine.text)
                        self.text_engine.finished = True
                else:
                    if self.text_auto_forward > 0:
                        self.text_auto_timer += dt
                        if self.text_auto_timer >= self.text_auto_forward:
                            self.text_auto_timer = 0.0
                            self._advance_dialogue()
                    else:
                        if self.z_just_pressed or (self.joystick and self.joystick.get_button(1)):
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
            self.player_locked = False

    # ---------------------------------------------------------

    def draw(self, surface):
        self.surface = surface
        if self.module and hasattr(self.module, "draw_front"):
            try:
                self.module.draw_front(self, surface)
            except Exception as e:
                print(f"[CutsceneLoader] Error in cutscene draw: {e}")
        if self.text_engine.text:
            self.text_engine.draw(
                x=self.text_x,
                y=self.text_y,
                text_color=(255, 255, 255),
                choice_color=(180, 180, 180),
                highlight_color=(255, 255, 0)
            )
        if self.module and hasattr(self.module, "draw_back"):
            try:
                self.module.draw_back(self, surface)
            except Exception as e:
                print(f"[CutsceneLoader] Error in cutscene draw: {e}")

