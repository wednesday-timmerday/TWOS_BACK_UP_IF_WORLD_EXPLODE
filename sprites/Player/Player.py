import pygame
import os
import json
import math
import cutscenes.loader as CutsceneLoaderModule
import interactables.loader as InteractableModule
from assetsLoader import Loader
from sprites.save.save import SaveOBJ
from ui.menu.save_menu import SaveMenu
from config.runtime_config import RuntimeJSON


def load_json_level_spec():
    level_spec_path = Loader("worlds").load("level-spec.json")
    if level_spec_path and os.path.exists(level_spec_path):
        with open(level_spec_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def check_collision_including_invis(world, rect, deactivated=None):
    if deactivated is None:
        deactivated = set()

    try:
        if world.check_collision(rect):
            return True
    except Exception:
        pass

    full_spec = getattr(world, "level_data", {}) or {}

    for w in full_spec.get("invis_walls", []):
        if len(w) < 5:
            continue

        wx = int(w[0])
        wy = int(w[1])
        ww = int(w[2])
        wh = int(w[3])
        name = str(w[4])

        if name in deactivated:
            continue

        wall_rect = pygame.Rect(wx, wy, ww, wh)
        if rect.colliderect(wall_rect):
            return True

    for p in full_spec.get("platforms", []):
        px = int(p.get("x", 0))
        py = int(p.get("y", 0))
        pw = int(p.get("width", 0))
        ph = int(p.get("height", 0))

        platform_rect = pygame.Rect(px, py, pw, ph)
        if rect.colliderect(platform_rect):
            return True

    return False


def check_collision_solid_only(world, rect):
    try:
        return bool(world.check_collision(rect))
    except Exception:
        return False


class Player:
    def __init__(self):
        self.coyote_time = 0.18
        self.coyote_timer = 0.0

        self.lebreah = False

        if self.lebreah:
            sprite_loader = Loader("sprites/Player/animation_frames/lebreah")
        else:
            sprite_loader = Loader("sprites/Player/animation_frames")

        sfx_loader = Loader("sprites/Player/Sfx")

        self.animations = {}
        self.animations_left = {}

        for folder in os.listdir(sprite_loader.load("")):
            folder_path = os.path.join(sprite_loader.load(""), folder)

            if os.path.isdir(folder_path):
                self.animations[folder] = []

                for file in os.listdir(folder_path):
                    file_path = os.path.join(folder_path, file)
                    self.animations[folder].append(file_path)

        for anim_name in list(self.animations.keys()):
            frames = []
            sprite_path = sprite_loader.load(anim_name)
            try:
                total_frames = len(
                    [n for n in os.listdir(sprite_path)
                     if os.path.isfile(os.path.join(sprite_path, n))]
                )
            except Exception:
                total_frames = 0

            for i in range(1, total_frames):
                try:
                    path = sprite_loader.load(f"{anim_name}/{anim_name}_{i}.png")
                    img = pygame.image.load(path).convert_alpha()
                except Exception:
                    img = pygame.Surface((40, 80), pygame.SRCALPHA)
                    img.fill((255, 0, 255, 100))
                frames.append(img)

            self.animations[anim_name] = frames
            self.animations_left[anim_name] = [pygame.transform.flip(f, True, False) for f in frames]

        self.sound_effects = {"Walk": []}
        for sfx_name in list(self.sound_effects.keys()):
            sfx = []
            sprite_path = sfx_loader.load(sfx_name)
            try:
                total_sfx = len(
                    [n for n in os.listdir(sprite_path)
                     if os.path.isfile(os.path.join(sprite_path, n))]
                )
            except Exception:
                total_sfx = 0

            for i in range(1, total_sfx):
                try:
                    path = sfx_loader.load(f"{sfx_name}/{sfx_name}_{i}.ogg")
                    sound = pygame.mixer.Sound(path)
                    sfx.append(sound)
                except Exception:
                    print("Pim's schuld...")

            self.sound_effects[sfx_name] = sfx

        self.curr_animation = "Idle"
        self.curr_frame = 0
        self.animation_timer = 0.0
        self.animation_speed = 0.12

        self.image = self.animations[self.curr_animation][self.curr_frame]
        self.image_right = self.image
        self.image_left = pygame.transform.flip(self.image, True, False)
        self.rect = self.image.get_rect()

        self.hit_box = pygame.Rect(5, 0, 6, 16)
        self.hitbox_offset_x = 0
        self.hitbox_offset_y = 0

        self.world_x = 303.0
        self.world_y = 114.0

        self.speed = 90.0
        self.speed_y = 0.0
        self.dir = 0
        self.on_ground = False
        self.can_move = True

        self._deactivated_walls = set()
        self._in_triggers = set()
        self._triggered_once = set()
        self._prev_z = False
        self._current_level = None

        self.save_obj = SaveOBJ()
        self.save_menu = SaveMenu()
        self.level_spec = load_json_level_spec()
        self.active_cutscene = None
        self.active_interactive = None
        self.active_fight = None

        self.joystick = None
        self.in_save_menu = False
        self.mass = 1.0
        self.event = None

        self.set_step_height_for_snapping = 5

        self.touching_wall_left = False
        self.touching_wall_right = False

        self.wall_slide_max_fall = 55.0
        self.wall_jump_y = -180.0
        self.wall_jump_push_speed = 125.0
        self.wall_jump_dir_lock_time = 0.14
        self.wall_jump_dir_lock_timer = 0.0
        self.wall_jump_push_dir = 0

        try:
            print(pygame.joystick.get_count())
            if pygame.joystick.get_count() > 0:
                self.joystick = pygame.joystick.Joystick(0)
        except Exception as e:
            print(e)

        try:
            loaded = self.save_obj.load_save()
        except Exception:
            loaded = None

        if loaded and isinstance(loaded, tuple):
            if len(loaded) >= 3:
                x, y, triggered_once = loaded[:3]
                try:
                    self.world_x, self.world_y = float(x), float(y)
                except Exception:
                    pass
                try:
                    self._triggered_once = set(str(i) for i in triggered_once)
                except Exception:
                    self._triggered_once = set()
            if len(loaded) >= 4:
                try:
                    self._deactivated_walls = set(str(w) for w in loaded[3])
                except Exception:
                    pass

        self.is_jumping = False
        self.coyote_time = 0.18
        self.jump_speed = -180
        self.max_jump_hold_time = 0.4
        self.last_level = None
        self.jump_buffer_time = 0.12
        self.jump_buffer_timer = 0.0

        if self.joystick:
            self.joystick.init()

        self.current_effect = None
        self._shadow_triggers_active = set()

    def refresh_animation(self):
        if self.lebreah:
            sprite_loader = Loader("sprites/Player/animation_frames/lebreah")
        else:
            sprite_loader = Loader("sprites/Player/animation_frames")

        for folder in os.listdir(sprite_loader.load("")):
            folder_path = os.path.join(sprite_loader.load(""), folder)

            if os.path.isdir(folder_path):
                self.animations[folder] = []

                for file in os.listdir(folder_path):
                    file_path = os.path.join(folder_path, file)
                    self.animations[folder].append(file_path)

        for anim_name in list(self.animations.keys()):
            frames = []
            sprite_path = sprite_loader.load(anim_name)
            try:
                total_frames = len(
                    [n for n in os.listdir(sprite_path)
                     if os.path.isfile(os.path.join(sprite_path, n))]
                )
            except Exception:
                total_frames = 0

            for i in range(1, total_frames):
                try:
                    path = sprite_loader.load(f"{anim_name}/{anim_name}_{i}.png")
                    img = pygame.image.load(path).convert_alpha()
                except Exception:
                    img = pygame.Surface((40, 80), pygame.SRCALPHA)
                    img.fill((255, 0, 255, 100))
                frames.append(img)

            self.animations[anim_name] = frames
            self.animations_left[anim_name] = [pygame.transform.flip(f, True, False) for f in frames]

    def update_hitbox(self):
        self.hit_box.topleft = (
            int(self.world_x + self.hitbox_offset_x),
            int(self.world_y + self.hitbox_offset_y)
        )

    def apply_spawn_point(self, level_target):
        level_key = f"level_{level_target}"
        level_data = self.level_spec.get(level_key, {})
        save_points = level_data.get("save_points", [])
        came_from = self.last_level

        for sp in save_points:
            if sp.get("type") == "spawn" and sp.get("came_from") == came_from:
                self.world_x = float(sp.get("pos_x", 160))
                self.world_y = float(sp.get("pos_y", 400))
                self.speed_y = 0.0
                return

        self.world_x = 160.0
        self.world_y = 400.0
        self.speed_y = 0.0

    def add_deact(self, name):
        if name:
            self._deactivated_walls.add(str(name))

    def remove_deact(self, name):
        self._deactivated_walls.discard(name)

    def get_deact(self):
        return set(self._deactivated_walls)

    def update(self, world, screen, dt, current_level=None, player=None, fight_loader=None):
        if not hasattr(self, "_prev_animation"):
            self._prev_animation = self.curr_animation

        if not hasattr(self, "_prev_frame"):
            self._prev_frame = self.curr_frame

        if self.curr_animation != self._prev_animation:
            self.curr_frame = 0
            self.animation_timer = 0.0
            self._prev_animation = self.curr_animation

        frames = self.animations.get(self.curr_animation, [])
        if not frames:
            placeholder = pygame.Surface((40, 80), pygame.SRCALPHA)
            placeholder.fill((255, 0, 255, 100))
            frames = [placeholder]
            self.animations[self.curr_animation] = frames

        self.animation_timer += dt
        while self.animation_timer >= self.animation_speed:
            self.animation_timer -= self.animation_speed
            self.curr_frame = (self.curr_frame + 1) % len(frames)

        if self.curr_animation == "Walking":
            if (self.curr_frame in (3, 6)) and (self._prev_frame != self.curr_frame):
                # self.sound_effects["Walk"][0].play()
                pass

        try:
            self.image = frames[self.curr_frame]
        except Exception as e:
            print(
                "Animation indexing error:", e,
                "anim=", self.curr_animation,
                "curr_frame=", self.curr_frame,
                "len_frames=", len(frames)
            )
            self.curr_frame = 0
            self.image = frames[0]

        try:
            self.image_right = self.animations[self.curr_animation][self.curr_frame]
        except Exception:
            placeholder = pygame.Surface((40, 80), pygame.SRCALPHA)
            placeholder.fill((255, 0, 255, 100))
            self.image_right = placeholder

        try:
            self.image_left = self.animations_left[self.curr_animation][self.curr_frame]
        except Exception:
            self.image_left = pygame.transform.flip(self.image_right, True, False)

        self.image = self.image_left if self.dir else self.image_right
        self.rect.size = self.image.get_size()

        self._prev_frame = self.curr_frame

        keys = pygame.key.get_pressed()
        dx = 0.0

        axis_x = axis_y = 0.0
        if self.joystick:
            try:
                axis_x = self.joystick.get_axis(0)
                axis_y = self.joystick.get_axis(1)
            except Exception as e:
                print(e)

        controls_allowed = self.can_move and not self.save_menu.visible and not self.active_fight

        hbx = self.hitbox_offset_x
        hby = self.hitbox_offset_y
        hb = self.hit_box
        deact = self._deactivated_walls

        self.wall_jump_dir_lock_timer = max(0.0, self.wall_jump_dir_lock_timer - dt)

        side_probe_h = max(1, hb.height - self.set_step_height_for_snapping)
        left_probe = pygame.Rect(int(self.world_x + hbx - 1), int(self.world_y + hby), 1, side_probe_h)
        right_probe = pygame.Rect(int(self.world_x + hbx + hb.width), int(self.world_y + hby), 1, side_probe_h)

        self.touching_wall_left = (not self.on_ground) and check_collision_solid_only(world, left_probe)
        self.touching_wall_right = (not self.on_ground) and check_collision_solid_only(world, right_probe)

        if controls_allowed:
            if self.wall_jump_dir_lock_timer > 0.0:
                dx = self.wall_jump_push_dir * self.wall_jump_push_speed * dt
                self.curr_animation = "Walking"
            else:
                if keys[pygame.K_LEFT] or keys[pygame.K_a] or axis_x < -0.5:
                    dx = -self.speed * dt
                    self.dir = 1
                    self.curr_animation = "Walking"
                elif keys[pygame.K_RIGHT] or keys[pygame.K_d] or axis_x > 0.5:
                    dx = self.speed * dt
                    self.dir = 0
                    self.curr_animation = "Walking"
                else:
                    self.curr_animation = "Idle"
                    if len(self.animations["Idle"]) > 0:
                        self.curr_frame = min(self.curr_frame, len(self.animations["Idle"]) - 1)
        else:
            dx = 0.0

        if self.current_effect == 1:
            dx *= 2.5

        try:
            jump_down = (
                keys[pygame.K_SPACE]
                or keys[pygame.K_w]
                or keys[pygame.K_UP]
                or (self.joystick and self.joystick.get_button(1))
            )
        except Exception:
            jump_down = False

        jump_just_pressed = jump_down and not getattr(self, "_prev_jump", False)
        self._prev_jump = jump_down

        if jump_just_pressed:
            self.jump_buffer_timer = self.jump_buffer_time
        else:
            self.jump_buffer_timer = max(0.0, self.jump_buffer_timer - dt)

        if self.on_ground:
            self.coyote_timer = self.coyote_time
        else:
            self.coyote_timer = max(0.0, self.coyote_timer - dt)

        wall_jumped = False

        if controls_allowed and jump_just_pressed and not self.on_ground and self.wall_jump_dir_lock_timer <= 0.0:
            if self.touching_wall_left:
                self.speed_y = self.wall_jump_y
                self.wall_jump_push_dir = 1
                self.wall_jump_dir_lock_timer = self.wall_jump_dir_lock_time
                self.dir = 0
                wall_jumped = True
            elif self.touching_wall_right:
                self.speed_y = self.wall_jump_y
                self.wall_jump_push_dir = -1
                self.wall_jump_dir_lock_timer = self.wall_jump_dir_lock_time
                self.dir = 1
                wall_jumped = True

            if wall_jumped:
                self.is_jumping = True
                self.jump_hold_timer = 0.0
                self.jump_buffer_timer = 0.0
                self.coyote_timer = 0.0

        if controls_allowed and not wall_jumped:
            if (
                self.jump_buffer_timer > 0.0
                and self.coyote_timer > 0.0
                and not self.is_jumping
            ):
                if self.current_effect == 2:
                    self.speed_y = self.jump_speed * 1.3
                else:
                    self.speed_y = self.jump_speed
                self.is_jumping = True
                self.jump_hold_timer = getattr(self, "max_jump_hold_time", 0.0)
                self.jump_buffer_timer = 0.0
                self.coyote_timer = 0.0

        gravity_jump_hold = 180
        gravity_jump_release = 480
        gravity_fall = 810

        if self.speed_y < 0:
            if getattr(self, "is_jumping", False) and jump_down and getattr(self, "jump_hold_timer", 0.0) > 0.0:
                gravity = gravity_jump_hold
                self.jump_hold_timer -= dt
            else:
                gravity = gravity_jump_release
            self.speed_y += gravity * dt
        else:
            if self.on_ground:
                self.speed_y = min(self.speed_y + gravity_fall * dt, 60.0)
            else:
                self.speed_y += gravity_fall * dt

        if (not self.on_ground) and self.speed_y > 0:
            holding_left = keys[pygame.K_LEFT] or keys[pygame.K_a] or axis_x < -0.5
            holding_right = keys[pygame.K_RIGHT] or keys[pygame.K_d] or axis_x > 0.5

            if (self.touching_wall_left and holding_left) or (self.touching_wall_right and holding_right):
                self.speed_y = min(self.speed_y, self.wall_slide_max_fall)

        dy = self.speed_y * dt

        h_test = pygame.Rect(
            int(self.world_x + dx + hbx),
            int(self.world_y + hby),
            hb.width,
            hb.height
        )

        if not check_collision_including_invis(world, h_test, deactivated=deact):
            self.world_x += dx
        elif dx != 0:
            stepped = False
            for step in range(1, 6):
                move_test = pygame.Rect(
                    int(self.world_x + dx + hbx),
                    int(self.world_y + hby - step),
                    hb.width, hb.height
                )
                stand_test = pygame.Rect(
                    int(self.world_x + hbx),
                    int(self.world_y + hby - step),
                    hb.width, hb.height
                )
                if (
                    not check_collision_including_invis(world, move_test, deactivated=deact)
                    and not check_collision_including_invis(world, stand_test, deactivated=deact)
                ):
                    self.world_x += dx
                    self.world_y -= step
                    stepped = True
                    break

        pre_move_y = self.world_y

        v_test = pygame.Rect(
            int(self.world_x + hbx),
            int(self.world_y + hby + dy),
            hb.width,
            hb.height
        )

        landed = False
        if check_collision_including_invis(world, v_test, deactivated=deact):
            if dy > 0:
                self.world_y = pre_move_y
                self.speed_y = 0.0
                landed = True
            else:
                self.world_y = pre_move_y
                self.speed_y = 0.0
                landed = False
        else:
            self.world_y += dy

        prev_on_ground = getattr(self, "on_ground", False)
        self.on_ground = landed

        if self.on_ground and not prev_on_ground:
            self.is_jumping = False
            self.jump_hold_timer = 0.0
            self.coyote_timer = self.coyote_time

        self.update_hitbox()

        side_probe_h = max(1, hb.height - self.set_step_height_for_snapping)
        left_probe = pygame.Rect(int(self.world_x + hbx - 1), int(self.world_y + hby), 1, side_probe_h)
        right_probe = pygame.Rect(int(self.world_x + hbx + hb.width), int(self.world_y + hby), 1, side_probe_h)

        self.touching_wall_left = (not self.on_ground) and check_collision_solid_only(world, left_probe)
        self.touching_wall_right = (not self.on_ground) and check_collision_solid_only(world, right_probe)

        if self.world_y > screen.get_height():
            self.apply_spawn_point(world.current_level)
            self.is_jumping = False
            self.jump_hold_timer = 0.0
            self.coyote_timer = self.coyote_time

        z_pressed = keys[pygame.K_z]
        z_just_pressed = z_pressed and not getattr(self, "_prev_z", False)

        if z_just_pressed and not self.save_menu.visible:
            self.save_menu.show()

        self._prev_z = z_pressed

        if self.save_menu.visible:
            self.in_save_menu = True
            action = self.save_menu.handle_input(keys)
            if action == "Save" and not getattr(self, "_saving", False):
                self._saving = True
            if action is None:
                self._saving = False
            return
        else:
            self.in_save_menu = False

        level_key = f"level_{getattr(world, 'current_level', current_level or 0)}"
        current_level_num = getattr(world, 'current_level', current_level or 0)

        if self._current_level != current_level_num:
            self._current_level = current_level_num
            self._in_triggers = set()

        triggers = self.level_spec.get(level_key, {}).get("triggers", [])

        player_rect = pygame.Rect(hb.x, hb.y, hb.width, hb.height)
        current_collisions = set()

        for idx, trigger in enumerate(triggers):
            trigger_id = trigger.get("id")
            trigger_key = trigger_id if trigger_id else f"_idx_{idx}"

            if trigger_key in self._triggered_once:
                continue

            trect = pygame.Rect(trigger["x"], trigger["y"], trigger["w"], trigger["h"])
            name = trigger.get("name", "").strip()

            if not player_rect.colliderect(trect):
                continue

            current_collisions.add(trigger_key)

            if trigger_key not in self._in_triggers:
                self._in_triggers.add(trigger_key)

                if name == "print":
                    print("Trigger COLLIDE!")
                    self._triggered_once.add(trigger_key)

                if name == "shadow_platform":
                    for data in world.boxEngine.shadow_data:
                        if data["rect"] == trect:
                            self.current_effect = data["curr_power"]
                            self._shadow_triggers_active.add(trigger_key)

                if self.active_cutscene and not getattr(self.active_cutscene, "running", False):
                    self.active_cutscene = None

                if self.active_interactive and not getattr(self.active_interactive, "running", False):
                    self.active_interactive = None

                if name.startswith("cutscene("):
                    cut_id = name[9:-1]
                    if not self.active_cutscene:
                        try:
                            self.active_cutscene = CutsceneLoaderModule.CutsceneLoader()
                            self.curr_animation = "Idle"
                            self.active_cutscene.world = world
                            self.active_cutscene.event = self.event
                            self.active_cutscene.player = self
                            self.active_cutscene.load(cut_id, self.joystick)
                            self.active_cutscene.trigger_idx = trigger_key
                        except Exception as e:
                            print("Error loading cutscene:", e)
                            self.active_cutscene = None

                if name.startswith("interactable("):
                    inter_id = name[13:-1]
                    if not self.active_cutscene:
                        try:
                            self.active_interactive = InteractableModule.Interactable()
                            self.curr_animation = "Idle"
                            self.active_interactive.world = world
                            self.active_interactive.event = self.event
                            self.active_interactive.player = self
                            self.active_interactive.load(inter_id, self.joystick)
                            self.active_interactive.trigger_idx = trigger_key
                        except Exception as e:
                            print("Error loading cutscene:", e)
                            self.active_cutscene = None

                elif name.startswith("deact_invis("):
                    self._deactivated_walls.add(name[13:-1])
                    self._triggered_once.add(trigger_key)

                elif name.startswith("goto("):
                    level_target = int(name[5:-1])
                    print("GO TO LEVEL:", level_target)
                    self.last_level = getattr(world, "current_level", None)
                    world.change_level(level_target, self)
                    self.apply_spawn_point(level_target)
                    if self.active_cutscene:
                        self.active_cutscene = None

                elif name.startswith("fight("):
                    fight_name = name[6:-1]
                    self.active_fight = fight_loader.load_fight(fight_name)
                    print(self.active_fight)
                    self.can_move = False

        self._in_triggers.intersection_update(current_collisions)

        shadow_triggers_in_range = set()
        for idx, trigger in enumerate(triggers):
            trigger_id = trigger.get("id")
            trigger_key = trigger_id if trigger_id else f"_idx_{idx}"
            name = trigger.get("name", "").strip()
            if name == "shadow_platform":
                trect = pygame.Rect(trigger["x"], trigger["y"], trigger["w"], trigger["h"])
                if player_rect.colliderect(trect):
                    shadow_triggers_in_range.add(trigger_key)

        exited_shadow = self._shadow_triggers_active - shadow_triggers_in_range
        if exited_shadow:
            self._shadow_triggers_active -= exited_shadow
            if not self._shadow_triggers_active:
                self.current_effect = None

        if self.active_interactive:
            trig = getattr(self.active_interactive, "trigger_idx", None)
            if trig not in self._in_triggers:
                self.active_interactive = None

        if self.active_cutscene:
            self.active_cutscene.update(dt, self)

        if self.active_interactive:
            self.active_interactive.update(dt)

    def draw(self, screen, world, true_screen):
        cam_x = getattr(world, "cam_x", 0)
        cam_y = getattr(world, "cam_y", 0)

        self.rect.size = self.image.get_size()
        draw_rect = self.rect.copy()

        float_center_x = self.world_x + self.hitbox_offset_x + self.hit_box.width / 2.0
        float_bottom_y = self.world_y + self.hitbox_offset_y + self.hit_box.height

        draw_rect.midbottom = (
            round(float_center_x - cam_x),
            round(float_bottom_y - cam_y)
        )

        try:
            img = self.image_left if self.dir else self.image_right
            screen.blit(img, draw_rect)
        except Exception:
            try:
                screen.blit(self.image, draw_rect)
            except Exception:
                pygame.draw.rect(screen, (0, 255, 0), draw_rect)

        if self.save_menu.visible:
            try:
                self.save_menu.draw(screen)
            except Exception:
                pass

        try:
            debug_hitbox = pygame.Rect(
                round(self.world_x + self.hitbox_offset_x - cam_x),
                round(self.world_y + self.hitbox_offset_y - cam_y),
                self.hit_box.width,
                self.hit_box.height
            )
            # pygame.draw.rect(screen, (255, 0, 0), debug_hitbox, 1)
        except Exception:
            pass