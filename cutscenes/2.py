import pygame
import types


def RandomAhhFunction(x: float) -> float:
    if x == 0:
        return 0
    elif x == 1:
        return 1
    elif x < 0.5:
        return (2 ** (20 * x - 10)) / 2
    else:
        return (2 - 2 ** (-20 * x + 10)) / 2


def find_phys_obj(world, name):
    name = name.lower()
    for engine in world.all_physic_objects:
        obj = engine.object
        if getattr(obj, "phys_type", "").lower() == name:
            return engine
    return None


class cutscene:
    def __init__(self, player, world, loader):
        self.dialogue_id = "2"
        self.player = player
        self.world = world
        self.loader = loader
        self.dt = 0

        self.shadowrock = next((e for e in world.enemies if e.__class__.__name__.lower() == "shadowrock"), None)
        self.mrtutor = next((e for e in world.enemies if e.__class__.__name__.lower() == "mrtutor"), None)
        self.hammer = next((e for e in world.enemies if e.__class__.__name__.lower() == "hammer"), None)
        self.orb = find_phys_obj(self.world, "orb")

        self.target_x = 750
        self.speed = 180.0
        self.hold_for = 0.0

        # Per-action persistent state (replaces hasattr guards scattered everywhere)
        self._state = {}

        # The sequence of (action, dialogue) pairs to execute in order.
        # Each entry is either:
        #   ("action",  method_name_string)   – call self.<method> every frame until it returns "YES"
        #   ("dialogue", text, speaker)        – show text, wait for player to advance
        #   ("choice",   prompt, [options])    – show choices, branch handled separately
        self._sequence = self._build_sequence()
        self._seq_index = 0
        self._waiting_dialogue = False
        self._waiting_choice = False

        # Patch camera once
        self._patch_camera()

    # ------------------------------------------------------------------
    # Camera patch (same logic as the commented-out version, cleaned up)
    # ------------------------------------------------------------------
    def _patch_camera(self):
        world = self.world
        loader = self.loader

        if not hasattr(loader, "fake_camera_x"):
            loader.fake_camera_x = getattr(self.player, "world_x", 0)
        if not hasattr(loader, "override_camera"):
            loader.override_camera = False
        if not hasattr(loader, "hold_timer"):
            loader.hold_timer = 0.0

        orig = world.update_camera

        def patched(self_world, player_x, player_y):
            if loader.override_camera:
                half_width = self_world.Screen_resolution[0] // 2
                self_world.cam_x = max(0, min(self_world.max_cam_x,
                                              loader.fake_camera_x - half_width))
                self_world.Cam_locked = (self_world.cam_x <= 0 or
                                         self_world.cam_x >= self_world.max_cam_x)
                self_world.cam_y = 0
            else:
                orig(player_x, player_y)

        world.update_camera = types.MethodType(patched, world)

    # ------------------------------------------------------------------
    # Sequence definition
    # ------------------------------------------------------------------
    def _build_sequence(self):
        D = "dialogue"
        A = "action"
        C = "choice"
        return [
            (A, "step_0"),
            (A, "move_tutor_1"),
            (D, "Mr. Tutorion: * O hello, you look&like you're new here.", "mrtutor"),
            (D, "Mr. Tutorion: * So that means you&gotta need a tutorial frooom!!!&MR TUUUTORIOOON!!!!!", "mrtutor"),
            (C, "Right?", ["Yes!", "No."]),
            # After the choice the run() method inserts the right dialogue branch
            # then continues from here:
            (D, "Mr Tutorion: * I want to give a&tutorial,^wait500you get a tutorial.", "mrtutor"),
            (A, "Move_cam_1"),
            (A, "hide_hammer"),
            (D, "Mr Tutorion: * See that orb&over there?", "mrtutor"),
            (A, "hide_hammer"),
            (D, "Mr. Tutorion: * If you want to&make progress you gotta push it&into the pit", "mrtutor"),
            (A, "hide_hammer"),
            (D, "Mr. Tutorion: * And its also the&only good lightsource here", "mrtutor"),
            (A, "hide_hammer"),
            (A, "start_shadowrock_text"),   # triggers Move_cam_2 + shadowrock line simultaneously
            (A, "Move_cam_2"),
            (A, "place_shadowrock"),
            (D, "Shadow Rock: * But what about&that lante-", "shadowrock"),
            (A, "Reset_cam"),
            (D, "Mr. Tutorion: * SHUT UP!", "mrtutor"),
            (A, "set_hammer"),
            (D, "Shadow Rock: * Wha-", "shadowrock"),
            (A, "release_the_hammer"),
            (D, "Shadow Rock: * Ouch!^special^wait500^endspecial&             * Fine, I'll go away...", "shadowrock"),
            (A, "drop_shadowrock"),
            (D, "Mr. Tutorion: * Now that that's&over with, lets&continue the tutorial!", "mrtutor"),
            (D, "Mr. Tutorion: * So as I was saying,&That's the orb.", "mrtutor"),
            (D, "Mr. Tutorion: * To make progress&you need to push it in the gap.&Try to do it.", "mrtutor"),
            (D, "Mr. Tutorion: * Random guy that I&don't know, and just&spawned in this world.", "mrtutor"),
            (A, "release_the_baby"),
            (A, "lock_the_baby"),
            (D, "Mr. Tutorion: * Great job!&Lets go to the next room.", "mrtutor"),
            (A, "release_the_baby_2"),
            (A, "follow_the_baby"),
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def RandomAhhFunction(self, x: float) -> float:
        if x == 0:
            return 0
        elif x == 1:
            return 1
        elif x < 0.5:
            return (2 ** (20 * x - 10)) / 2
        else:
            return (2 - 2 ** (-20 * x + 10)) / 2

    def approach(self, current, target, max_delta):
        if current < target:
            return min(current + max_delta, target)
        else:
            return max(current - max_delta, target)

    def _x_pressed(self, joystick):
        joy_btn = joystick.get_button(1) if joystick else False
        return (getattr(self.loader, "x_just_pressed", False)
                or pygame.key.get_pressed()[pygame.K_x]
                or joy_btn)

    def _z_pressed(self, joystick):
        joy_btn = joystick.get_button(0) if joystick else False
        return (getattr(self.loader, "z_just_pressed", False)
                or joystick.get_button(0) if joystick else False
                or joy_btn)

    # ------------------------------------------------------------------
    # Main run – call every frame
    # ------------------------------------------------------------------
    def run(self, dt, player, world, joystick, event):
        self.dt = dt
        self.player = player
        self.world = world

        if joystick is None:
            class _DummyJoy:
                def get_button(self, i): return False
                def get_axis(self, i): return 0
            joystick = _DummyJoy()

        te = self.loader.text_engine

        # --- waiting for player to advance dialogue ---
        if self._waiting_dialogue:
            te.update(dt)
            if self._x_pressed(joystick) and not te.finished:
                te.char_index = len(te.text)
                te.finished = True
            elif te.finished and self._z_pressed(joystick):
                self._waiting_dialogue = False
                self._seq_index += 1
            return

        # --- waiting for player to pick a choice ---
        if self._waiting_choice:
            te.update(dt)
            keys = pygame.key.get_pressed()
            choice = te.handle_choice_input(keys)
            if choice:
                self._waiting_choice = False
                # Insert the appropriate branch dialogue right after current position
                if choice == "Yes!":
                    branch = [("dialogue",
                                "Mr. Tutorion: * Alright then!&lets start",
                                "mrtutor")]
                else:
                    branch = [
                        ("dialogue",
                         "Mr Tutorion: * Well you don't have&a choice.",
                         "mrtutor"),
                    ]
                # Splice branch into sequence after the choice entry
                self._sequence = (self._sequence[:self._seq_index + 1]
                                  + branch
                                  + self._sequence[self._seq_index + 1:])
                self._seq_index += 1
            return

        # --- sequence exhausted ---
        if self._seq_index >= len(self._sequence):
            self.loader.running = False
            return

        entry = self._sequence[self._seq_index]
        kind = entry[0]

        if kind == "dialogue":
            _, text, speaker = entry
            te.start_text(text, speaker)
            self._waiting_dialogue = True
            # Don't advance index yet; the dialogue-wait block above will do it

        elif kind == "choice":
            _, prompt, options = entry
            te.start_choices(prompt, options)
            self._waiting_choice = True

        elif kind == "action":
            _, method_name = entry
            method = getattr(self, method_name)
            result = method()
            if result == "YES":
                self._seq_index += 1
            # If not "YES", we stay on this entry and call it again next frame

    # ------------------------------------------------------------------
    # Actions  (return "YES" when done, None/nothing to keep running)
    # ------------------------------------------------------------------
    def step_0(self):
        self.shadowrock.world_y = -9999
        self.mrtutor.world_x = 332
        self.player.can_move = False
        self.player._deactivated_walls.add("wall_2")
        return "YES"

    def move_tutor_1(self):
        # Use self._state to persist values across frames
        s = self._state.setdefault("move_tutor_1", {
            "t": 0.0,
            "duration": 10.0,
            "start_x": self.mrtutor.world_x,
            "target_x": 70,
        })

        s["t"] += self.dt
        t = min(s["t"] / s["duration"], 1.0)
        ease = self.RandomAhhFunction(t)

        self.mrtutor.world_x = s["start_x"] + (s["target_x"] - s["start_x"]) * ease
        self.mrtutor.world_y = 119

        if t >= 1.0:
            self.player.dir = 0
            return "YES"

    def Move_cam_1(self):
        self.loader.override_camera = True
        self.loader.fake_camera_x = self.approach(
            self.loader.fake_camera_x, self.target_x, self.speed * self.dt)
        if self.loader.fake_camera_x == self.target_x:
            self.loader.hold_timer = 0.0
            return "YES"

    def Move_cam_2(self):
        self.target_x = 900
        self.loader.override_camera = True
        self.loader.fake_camera_x = self.approach(
            self.loader.fake_camera_x, self.target_x, self.speed * self.dt)
        if self.loader.fake_camera_x == self.target_x:
            self.loader.hold_timer = 0.0
            return "YES"

    def Reset_cam(self):
        self.loader.override_camera = False
        return "YES"   # instant – no waiting needed

    def hide_hammer(self):
        self.hammer.world_x = 100000
        self.hammer.world_y = 100000
        return "YES"

    def start_shadowrock_text(self):
        # Fires once, camera pan happens in Move_cam_2
        return "YES"

    def place_shadowrock(self):
        self.shadowrock.world_x = 138
        self.shadowrock.world_y = 157
        return "YES"

    def set_hammer(self):
        self.hammer.world_x = 138
        self.hammer.world_y = -50
        return "YES"

    def release_the_hammer(self):
        hammer_fall_pos = 360
        hammer_fall_speed = 216
        self.hammer.world_y = self.approach(
            self.hammer.world_y, hammer_fall_pos, hammer_fall_speed * self.dt)
        if self.hammer.world_y >= hammer_fall_pos:
            return "YES"

    def drop_shadowrock(self):
        shadowrock_fall_speed = 120
        shadowrock_fall_pos = 360
        self.shadowrock.world_y = self.approach(
            self.shadowrock.world_y, shadowrock_fall_pos, shadowrock_fall_speed * self.dt)
        if self.shadowrock.world_y >= shadowrock_fall_pos:
            return "YES"

    def release_the_baby(self):
        self.player.can_move = True
        self.loader.text_engine.start_text("", "")
        if self.orb.object.hit_cutscene:
            return "YES"

    def lock_the_baby(self):
        self.player.can_move = False
        self.player.curr_animation = "Idle"
        self.mrtutor.world_x = self.approach(
            self.mrtutor.world_x, self.player.world_x - 60, 240 * self.dt)
        if self.mrtutor.world_x >= self.player.world_x - 60:
            return "YES"

    def release_the_baby_2(self):
        self.loader.text_engine.start_text("", "")
        self.player.can_move = True
        return "YES"

    def follow_the_baby(self):
        self.player._deactivated_walls.add("wall_3")
        if not self.world.current_level == 4:
            if self.player.dir <= 0.0:
                self.mrtutor.world_x = self.player.world_x - 18
            else:
                self.mrtutor.world_x = self.player.world_x + 18
            self.mrtutor.world_y = self.player.world_y - 24
        else:
            if hasattr(self.player, "_triggered_once") and hasattr(self.loader, "trigger_idx"):
                self.player._triggered_once.add(self.loader.trigger_idx)
            return "YES"