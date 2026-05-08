import types
import pygame


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

        self.shadowrock = next(
            (e for e in world.enemies if e.__class__.__name__.lower() == "shadowrock"),
            None
        )
        self.mrtutor = next(
            (e for e in world.enemies if e.__class__.__name__.lower() == "mrtutor"),
            None
        )
        self.hammer = next(
            (e for e in world.enemies if e.__class__.__name__.lower() == "hammer"),
            None
        )
        self.orb = find_phys_obj(self.world, "orb")

        self.target_x = 750
        self.speed = 180.0
        self.hold_for = 0.0

        self._state = {}

        # NEW: hammer collision state
        self.hammer_hit = False

        self._patch_camera()

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
                self_world.cam_x = max(
                    0,
                    min(self_world.max_cam_x, loader.fake_camera_x - half_width)
                )
                self_world.Cam_locked = (
                    self_world.cam_x <= 0 or self_world.cam_x >= self_world.max_cam_x
                )
                self_world.cam_y = 0
            else:
                orig(player_x, player_y)

        world.update_camera = types.MethodType(patched, world)

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

    # ---------------- CUTSCENE STEPS ---------------- #

    def step_0(self):
        if self.shadowrock is not None:
            self.shadowrock.world_y = -9999
        if self.mrtutor is not None:
            self.mrtutor.world_x = 332
        self.player._deactivated_walls.add("wall_2")
        return "YES"

    def move_tutor_1(self):
        if self.mrtutor is None:
            return "YES"

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
            self.loader.fake_camera_x,
            self.target_x,
            self.speed * self.dt
        )
        if self.loader.fake_camera_x == self.target_x:
            self.loader.hold_timer = 0.0
            return "YES"

    def Move_cam_2(self):
        self.target_x = 900
        self.loader.override_camera = True
        self.loader.fake_camera_x = self.approach(
            self.loader.fake_camera_x,
            self.target_x,
            self.speed * self.dt
        )
        if self.loader.fake_camera_x == self.target_x:
            self.loader.hold_timer = 0.0
            return "YES"

    def Reset_cam(self):
        self.loader.override_camera = False
        return "YES"

    def hide_hammer(self):
        if self.hammer is not None:
            self.hammer.world_x = 100000
            self.hammer.world_y = 100000
        return "YES"

    def start_shadowrock_text(self):
        return "YES"

    def place_shadowrock(self):
        if self.shadowrock is not None:
            self.shadowrock.world_x = 138
            self.shadowrock.world_y = 157
        return "YES"

    def set_hammer(self):
        if self.hammer is not None:
            self.hammer.world_x = 138
            self.hammer.world_y = -50
        return "YES"

    def release_the_hammer(self):
        if self.hammer is None:
            return "YES"

        hammer_fall_pos = 360
        hammer_fall_speed = 216

        self.hammer.world_y = self.approach(
            self.hammer.world_y,
            hammer_fall_pos,
            hammer_fall_speed * self.dt
        )

        # Check collision
        if self.shadowrock is not None and not self.hammer_hit:
            hit_x = abs(self.hammer.world_x - self.shadowrock.world_x) < 30
            hit_y = abs(self.hammer.world_y - self.shadowrock.world_y) < 30
            if hit_x and hit_y:
                self.hammer_hit = True

        # Once hit, drag shadowrock along with hammer at same speed
        if self.hammer_hit and self.shadowrock is not None:
            self.shadowrock.world_y = self.approach(
                self.shadowrock.world_y,
                hammer_fall_pos,
                hammer_fall_speed * self.dt
            )

        if self.hammer.world_y >= hammer_fall_pos:
            return "YES"

    def release_the_baby(self):
        self.player.can_move = True
        if hasattr(self.loader, "text_engine"):
            self.loader.text_engine.start_text("", "")
        if self.orb is not None and getattr(self.orb.object, "hit_cutscene", False):
            return "YES"

    def lock_the_baby(self):
        self.player.can_move = False
        self.player.curr_animation = "Idle"

        if self.mrtutor is None:
            return "YES"

        target_x = self.player.world_x - 60
        self.mrtutor.world_x = self.approach(
            self.mrtutor.world_x,
            target_x,
            240 * self.dt
        )

        if abs(self.mrtutor.world_x - target_x) <= 0.5:
            return "YES"

    def release_the_baby_2(self):
        if hasattr(self.loader, "text_engine"):
            self.loader.text_engine.start_text("", "")
        return "YES"

    def follow_the_baby(self):
        self.player.can_move = True
        self.player._deactivated_walls.add("wall_3")

        if self.world.current_level != 4:
            if self.mrtutor is not None:
                if self.player.dir <= 0.0:
                    self.mrtutor.world_x = self.player.world_x - 18
                else:
                    self.mrtutor.world_x = self.player.world_x + 18
                self.mrtutor.world_y = self.player.world_y - 24
            return

        if hasattr(self.player, "_triggered_once") and hasattr(self.loader, "trigger_idx"):
            self.player._triggered_once.add(self.loader.trigger_idx)
        return "YES"