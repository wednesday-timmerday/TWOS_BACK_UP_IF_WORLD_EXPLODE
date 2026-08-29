import json
import math
import os
import random

import pygame

import cutscenes.loader as CutsceneLoaderModule
import interactables.loader as InteractableModule
from assetsLoader import Loader
from BtnHandeler import btnHandeler
from sprites.save.save import SaveOBJ
from ui.menu.midgame import Menu
from ui.menu.save_menu import SaveMenu

import ui.fight.fight as FightModule


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
        wx, wy, ww, wh = int(w[0]), int(w[1]), int(w[2]), int(w[3])
        name = str(w[4])
        if name in deactivated:
            continue
        if rect.colliderect(pygame.Rect(wx, wy, ww, wh)):
            return True

    for p in full_spec.get("platforms", []):
        px = int(p.get("x", 0))
        py = int(p.get("y", 0))
        pw = int(p.get("width", 0))
        ph = int(p.get("height", 0))
        if rect.colliderect(pygame.Rect(px, py, pw, ph)):
            return True

    return False


def check_collision_solid_only(world, rect):
    try:
        return bool(world.check_collision(rect))
    except Exception:
        return False


# --- Death screen phase constants --------------------------------------------
_DS_FADE_IN = "fade_in"  # black overlay fades in
_DS_HOLD = "hold"  # fully black, brief pause
_DS_OLD_OUT = "old_out"  # old lives count slides/fades away
_DS_NEW_IN = "new_in"  # new lives count slides/bounces in
_DS_DONE = "done"  # animation complete, waiting for timer


class Player:
    def __init__(self, screen):
        # -- Character select ----------------------------------------------
        self.lebreah = False
        self.screen = screen

        sprite_loader = Loader(
            "sprites/Player/animation_frames/lebreah"
            if self.lebreah
            else "sprites/Player/animation_frames"
        )
        sfx_loader = Loader("sprites/Player/Sfx")

        # Animations --
        self.animations = {}
        self.animations_left = {}
        self._load_animations(sprite_loader)

        #  Sound effects -
        self.sound_effects = {"Walk": []}
        self._load_sfx(sfx_loader)

        #  Animation state -
        self.curr_animation = "Idle"
        self.curr_frame = 0
        self.animation_timer = 0.0
        self.animation_speed = 0.12
        self._prev_animation = "Idle"
        self._prev_frame = 0

        self.image = self.animations[self.curr_animation][0]
        self.image_right = self.image
        self.image_left = pygame.transform.flip(self.image, True, False)
        self.rect = self.image.get_rect()

        #  Hitbox
        self.hit_box = pygame.Rect(5, 0, 6, 16)
        self.hitbox_offset_x = 0
        self.hitbox_offset_y = 0

        #  World position
        self.world_x = 303.0
        self.world_y = 130.0

        #  Movement
        self.speed = 90.0
        self.speed_y = 0.0
        self.dir = 0  # 0 = right, 1 = left
        self.on_ground = False
        self.can_move = False  # we set this to false bcz of the frame-1 bug, in later build we need to check if the first cutscene has triggered
        self.dt = 0.0
        self.set_step_height_for_snapping = 5

        #  Jump
        self.is_jumping = False
        self.jump_speed = -180
        self.max_jump_hold_time = 0.4
        self.jump_hold_timer = 0.0
        self.jump_buffer_time = 0.12
        self.jump_buffer_timer = 0.0
        self._prev_jump = False

        #  Coyote time -
        self.coyote_time = 0.18
        self.coyote_timer = 0.0

        #  Wall slide / wall jump
        self.touching_wall_left = False
        self.touching_wall_right = False
        self.wall_slide_max_fall = 55.0
        self.wall_jump_y = -200.0
        self.wall_jump_push_speed = 85.0
        self.wall_jump_dir_lock_time = 0.18
        self.wall_jump_dir_lock_timer = 0.0
        self.wall_jump_push_dir = 0

        #  Trigger / level state -
        self._deactivated_walls = set()
        self._in_triggers = set()
        self._triggered_once = set()
        self._current_level = None
        self.last_level = None

        #  Save / menu -
        self.save_obj = SaveOBJ()
        self.save_menu = SaveMenu()
        self.in_save_menu = False
        self._prev_z = False
        self._saving = False

        #  Interactable Z input -
        self._prev_z_interactable = False
        self.z_just_pressed_interactable = False

        #  Active scenes / fight -
        self.active_cutscene = None
        self.active_interactive = None
        self.active_fight = None
        self.event = None

        #  Effects -
        self.current_effect = None
        self._shadow_triggers_active = set()
        self.mass = 1.0

        #  Death knockback
        self.death_knockback_x = 0.0

        #  Level spec
        self.level_spec = load_json_level_spec()

        #  Lives -
        self.lives = 6

        #  Death state -
        self.dead = False
        self.dead_timer = 0.0
        self.dead_display_time = 3.5

        self.freeze_frame_duration = 0.6
        self.freeze_frame_timer = 0.0
        self.freeze_frame_active = False
        self.freeze_frame_snapshot = None

        self.death_walk_active = False
        self.death_walk_timer = 0.0
        self.death_walk_duration = 1.2

        self._ds_phase = _DS_FADE_IN
        self._ds_phase_timer = 0.0
        self._ds_fade_in_dur = 0.45
        self._ds_hold_dur = 0.20
        self._ds_old_out_dur = 0.45
        self._ds_new_in_dur = 0.55
        self._ds_lives_before = 6

        self._death_font_large = None
        self._death_font_small = None

        # Respawn protection + collision gate
        self.respawn_protect_time = 0.75
        self.respawn_protect_timer = self.respawn_protect_time
        self.collision_enabled = True

        #  Frozen / misc -
        self.frozen = False
        self.jump_down = False

        self._cam_catchup_active = False
        self._cam_catchup_timer = 0.0
        self._cam_catchup_dur = 0.4 
        self._cam_catchup_start_y = 0.0  
        self._cam_catchup_target_y = 0.0  

        #  Camera override / lock -
        self.camera_y_lock = False
        self.camera_y_lock_target = None
        self.camera_y_lock_speed = None

        #  Joystick
        self.joystick = None
        try:
            if pygame.joystick.get_count() > 0:
                self.joystick = pygame.joystick.Joystick(0)
                self.joystick.init()
        except Exception as e:
            print(e)

        #  Load save -
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

        self.offset_x = 0
        self.offset_y = 0
        self.dash_active = False
        self.dash_timer = 0.0
        self.dash_duration = 0.3
        self.dash_cooldown_timer = 0.0
        self.dash_cooldown_time = 2.0
        self.dash_cooldown_timer_time = False
        self.in_death_scene = False
        self.fight_loader = None
        self.show_encounter = False
        self.encounter_image = pygame.image.load(sprite_loader.load("encounter/!.png"))
        self.temp_timer = 0.0
        self.incutscene = False
        self.atk = 20
        self.defense = 5
        self.money = 0
        self.hp = 10
        self.max_hp = 10
        self.world = None
        self.bg_music_name = None
        try:
            self.midgamemenu = Menu(screen, player=self)
        except Exception as e:
            print(f"KYU {e}")

        self.mouse_flag = False
        self.btnhandeler = btnHandeler()
        self.items = [{"name": "dog", "short_name": "dog", "type": "heal", "heal_amount": 9999999999999999999999999999999999999999999999}, {"name": "default", "short_name": "def", "type": "heal", "heal_amount": 17}, {"name": "default", "short_name": "def", "type": "heal", "heal_amount": 17}] # How do items work: {"name": "carrot", "short_name": "carr", "type": "heal", "heal_amount" etc.}
        self.name = "micheal jackson"
    # -
    # Private helpers
    # -
    # 
     
    def handle_item_used(self, item_name):
        for i, item in enumerate(self.items):
            if item["short_name"] == item_name:
                self.items.pop(i)
                if item["type"] == "heal":
                    self.hp += item["heal_amount"]
                    if self.hp > self.max_hp:
                        self.hp = self.max_hp
                break

    def _death_fonts(self):
        """Lazily init death fonts (pygame.font must already be initialised)."""
        if self._death_font_large is None:
            try:
                self._death_font_large = pygame.font.SysFont("Arial", 12, bold=True)
                self._death_font_small = pygame.font.SysFont("Arial", 6)
            except Exception:
                pass
        return self._death_font_large, self._death_font_small

    def _load_animations(self, sprite_loader):
        # Load all animation folders
        root = sprite_loader.load("")
        for folder in os.listdir(root):
            folder_path = os.path.join(root, folder)
            if not os.path.isdir(folder_path):
                continue
            self.animations[folder] = []

        # For all folder names
        for anim_name in list(self.animations.keys()):
            frames = []
            sprite_path = sprite_loader.load(anim_name)
            try:
                total_frames = len(
                    [
                        n
                        for n in os.listdir(sprite_path)
                        if os.path.isfile(os.path.join(sprite_path, n))
                        and n.lower().startswith(anim_name.lower() + "_")
                        and n.lower().endswith(".png")
                    ]
                )
            except Exception:
                total_frames = 0

            for i in range(1, total_frames + 1):
                img = None
                try:
                    path = sprite_loader.load(f"{anim_name}/{anim_name}_{i}.png")
                    img = pygame.image.load(path).convert_alpha()
                except Exception as e:
                    print(f"Error loading frame {i} for animation {anim_name}: {e}")
                if img is not None:
                    frames.append(img)

            self.animations[anim_name] = frames
            self.animations_left[anim_name] = [
                pygame.transform.flip(f, True, False) for f in frames
            ]

    def _load_sfx(self, sfx_loader):
        for sfx_name in list(self.sound_effects.keys()):
            sfx = []
            sprite_path = sfx_loader.load(sfx_name)
            try:
                total_sfx = len(
                    [
                        n
                        for n in os.listdir(sprite_path)
                        if os.path.isfile(os.path.join(sprite_path, n))
                        and n.lower().startswith(sfx_name.lower() + "_")
                        and n.lower().endswith(".ogg")
                    ]
                )
            except Exception:
                total_sfx = 0

            for i in range(1, total_sfx + 1):
                try:
                    path = sfx_loader.load(f"{sfx_name}/{sfx_name}_{i}.ogg")
                    sfx.append(pygame.mixer.Sound(path))
                except Exception:
                    print("SFX load failed")

            self.sound_effects[sfx_name] = sfx

    def _reset_after_respawn(self):
        self.speed_y = 0.0
        self.death_knockback_x = 0.0
        self.is_jumping = False
        self.jump_hold_timer = 0.0
        self.jump_buffer_timer = 0.0
        self.coyote_timer = 0.0
        self._prev_jump = False
        self.jump_down = False
        self.on_ground = False
        self.curr_animation = "Idle"
        self.curr_frame = 0
        self.animation_timer = 0.0
        self._prev_animation = "Idle"
        self.respawn_protect_timer = self.respawn_protect_time
        self.freeze_frame_active = False
        self.freeze_frame_timer = 0.0
        self.freeze_frame_snapshot = None
        self.death_walk_active = False
        self.death_walk_timer = 0.0
        self.collision_enabled = True
        self._cam_catchup_active = False  # cancel any in-flight catch-up on respawn
        self._cam_catchup_timer = 0.0
        self.frozen = False
        self.clear_camera_y_lock()

    def lock_camera_y(self, target_y, speed=None):
        # Lock the world camera to a specific world-space Y target.
        self.camera_y_lock = True
        self.camera_y_lock_target = float(target_y)
        self.camera_y_lock_speed = speed

    def clear_camera_y_lock(self):
        # Return the camera to normal player-follow mode.
        self.camera_y_lock = False
        self.camera_y_lock_target = None
        self.camera_y_lock_speed = None

    # -
    # Public helpers
    # -

    def refresh_animation(self):
        sprite_loader = Loader(
            "sprites/Player/animation_frames/lebreah"
            if self.lebreah
            else "sprites/Player/animation_frames"
        )
        self._load_animations(sprite_loader)

    def update_hitbox(self):
        self.hit_box.topleft = (
            int(self.world_x + self.hitbox_offset_x),
            int(self.world_y + self.hitbox_offset_y),
        )

    def apply_spawn_point(self, level_target):
        print("run")
        level_key = f"level_{level_target}"
        level_data = self.level_spec.get(level_key, {})
        came_from = str(self.last_level) if self.last_level is not None else None

        for sp in level_data.get("save_points", []):
            if sp.get("type") == "spawn" and str(sp.get("came_from")) == came_from:
                self.world_x = float(sp.get("pos_x", 160))
                self.world_y = float(sp.get("pos_y", 0))
                self.speed_y = 0.0
                return

        # fallback
        self.world_x = 160.0
        self.world_y = 0.0
        self.speed_y = 0.0

    def add_deact(self, name):
        if name:
            self._deactivated_walls.add(str(name))

    def remove_deact(self, name):
        self._deactivated_walls.discard(name)

    def get_deact(self):
        return set(self._deactivated_walls)

    def update_interactable_z_input(self, keys, joystick):
        """Update and return Z input state for interactables.

        Returns True if Z was just pressed this frame.
        """
        z_pressed = (
            self.btnhandeler.get_btn_pressed("z")
            or self.btnhandeler.get_btn_pressed("y")
            or (joystick and joystick.get_button(1))
        )
        self.z_just_pressed_interactable = z_pressed and not self._prev_z_interactable
        self._prev_z_interactable = z_pressed
        return self.z_just_pressed_interactable

    def start_encounter(self, name, idx=-9999999):
        self.show_encounter = True
        self.can_move = False
        self.temp_timer += self.dt
        if (
            self.temp_timer >= 3
        ):  # This needs to be the length of the encounter sfx... TODO: get the sfx and make the timings corr
            self.curr_animation = "imnotracist"
            self.show_encounter = False
            if self.temp_timer >= 7:
                self.fight_loader = FightModule.Fight(self.screen, self.true_screen, self, self.world)
                self.active_fight = self.fight_loader.load_fight(name, idx)
                self.show_encounter = False
                self.temp_timer = 0
                return 1

    # -----------------------------
    # Die
    # -----------------------------

    def die(self, world):
        if (
            self.dead
            or self.freeze_frame_active
            or self.death_walk_active
            or self.respawn_protect_timer > 0.0
        ):
            return

        self._ds_lives_before = self.lives
        self.curr_animation = "Idle"
        self.curr_frame = 0
        self.animation_timer = 0.0
        self.freeze_frame_active = True
        self.freeze_frame_timer = 0.0
        self.freeze_frame_snapshot = None
        self.can_move = False
        self.is_jumping = True
        self.jump_hold_timer = 0.0
        self.coyote_timer = 0.0
        self.speed_y = -150.0
        self.jump_down = True
        self.jump_hold_timer = 999.0
        self.on_ground = False
        self.collision_enabled = False

    #
    # Update
    #

    def update(
        self, world, screen, dt, current_level=None, player=None, fight_loader=None
    ):
        self.dt = dt
        self.fight_loader = fight_loader
        self.world = world
        if self.respawn_protect_timer > 0.0:
            self.respawn_protect_timer = max(0.0, self.respawn_protect_timer - dt)


        if not self.active_fight:
            self.midgamemenu.update(dt)

        # ----------------------------------------------------------------
        # Phase 1 - Freeze frame
        # ----------------------------------------------------------------
        if self.freeze_frame_active:
            self.freeze_frame_timer += dt
            if self.freeze_frame_timer >= self.freeze_frame_duration:
                self.freeze_frame_active = False
                self.freeze_frame_snapshot = None
                self.death_walk_active = True
                self.death_walk_timer = 0.0
            # Physics still run below (don't return yet)

        # ----------------------------------------------------------------
        # Phase 2 - Death walk
        # ----------------------------------------------------------------
        elif self.death_walk_active:
            self.death_walk_timer += dt
            if self.death_walk_timer >= self.death_walk_duration:
                self.death_walk_active = False
                self.dead = True
                self.dead_timer = 0.0
                self.lives -= 1
                self._ds_phase = _DS_FADE_IN
                self._ds_phase_timer = 0.0

        # ----------------------------------------------------------------
        # Phase 3 - Death screen
        # ----------------------------------------------------------------
        elif self.dead:
            self.dead_timer += dt
            self._ds_phase_timer += dt

            if (
                self._ds_phase == _DS_FADE_IN
                and self._ds_phase_timer >= self._ds_fade_in_dur
            ):
                self._ds_phase = _DS_HOLD
                self._ds_phase_timer = 0.0
            elif (
                self._ds_phase == _DS_HOLD and self._ds_phase_timer >= self._ds_hold_dur
            ):
                self._ds_phase = _DS_OLD_OUT
                self._ds_phase_timer = 0.0
            elif (
                self._ds_phase == _DS_OLD_OUT
                and self._ds_phase_timer >= self._ds_old_out_dur
            ):
                self._ds_phase = _DS_NEW_IN
                self._ds_phase_timer = 0.0
            elif (
                self._ds_phase == _DS_NEW_IN
                and self._ds_phase_timer >= self._ds_new_in_dur
            ):
                self._ds_phase = _DS_DONE
                self._ds_phase_timer = 0.0
            elif (
                self._ds_phase == _DS_DONE
                and self._ds_phase_timer >= self.dead_display_time
            ):
                self.dead = False

            # Update the death cutscene (lives == 0) while dead
            if self.active_cutscene:
                self.active_cutscene.update(dt, self)

            if self.dead_timer >= self.dead_display_time: #and not self.active_cutscene:
                self.dead = False
                self.dead_timer = 0.0
                self.can_move = True
                self.apply_spawn_point(world.current_level)
                self._reset_after_respawn()
            return

        # ----------------------------------------------------------------
        # Animation frame advance (held during camera catch-up freeze)
        # ----------------------------------------------------------------
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

        if not self._cam_catchup_active:
            self.animation_timer += dt
            while self.animation_timer >= self.animation_speed:
                self.animation_timer -= self.animation_speed
                self.curr_frame = (self.curr_frame + 1) % len(frames)

        self._prev_frame = self.curr_frame

        try:
            self.image = frames[self.curr_frame]
        except Exception:
            self.curr_frame = 0
            self.image = frames[0]

        try:
            self.image_right = self.animations[self.curr_animation][self.curr_frame]
        except Exception:
            self.image_right = pygame.Surface((40, 80), pygame.SRCALPHA)
            self.image_right.fill((255, 0, 255, 100))

        try:
            self.image_left = self.animations_left[self.curr_animation][self.curr_frame]
        except Exception:
            self.image_left = pygame.transform.flip(self.image_right, True, False)

        self.image = self.image_left if self.dir else self.image_right
        self.rect.size = self.image.get_size()

        #  Input -------------------------------
        keys = pygame.key.get_pressed()
        axis_x = 0.0
        if self.joystick:
            try:
                axis_x = self.joystick.get_axis(0)
            except Exception:
                pass

        controls_allowed = (
            self.can_move
            and not self.save_menu.visible
            and not self.active_fight
            and not self.freeze_frame_active
            and not self.death_walk_active
            and not self._cam_catchup_active
        )

        hbx = self.hitbox_offset_x
        hby = self.hitbox_offset_y
        hb = self.hit_box
        deact = self._deactivated_walls

        ignore_collisions = (
            self.dead or self.death_walk_active or (not self.collision_enabled)
        )

        # -- Wall touch probes ---------------------------------------------
        if not ignore_collisions and not self._cam_catchup_active:
            self.wall_jump_dir_lock_timer = max(0.0, self.wall_jump_dir_lock_timer - dt)
            side_probe_h = max(1, hb.height - self.set_step_height_for_snapping)
            left_probe = pygame.Rect(
                int(self.world_x + hbx - 3), int(self.world_y + hby), 3, side_probe_h
            )
            right_probe = pygame.Rect(
                int(self.world_x + hbx + hb.width),
                int(self.world_y + hby),
                3,
                side_probe_h,
            )
            self.touching_wall_left = (
                not self.on_ground
            ) and check_collision_solid_only(world, left_probe)
            self.touching_wall_right = (
                not self.on_ground
            ) and check_collision_solid_only(world, right_probe)
        else:
            self.touching_wall_left = False
            self.touching_wall_right = False

        # -- Horizontal movement -------------------------------------------
        dx = 0.0
        world.is_timer_active = False
        if controls_allowed:
            if self.wall_jump_dir_lock_timer > 0.0:
                dx = self.wall_jump_push_dir * self.wall_jump_push_speed * dt
                self.curr_animation = "Walking"
            else:
                if self.btnhandeler.get_btn_pressed("left") or axis_x < -0.5:
                    world.is_timer_active = True
                    dx = -self.speed * dt
                    self.dir = 1
                    self.curr_animation = "Walking"
                elif self.btnhandeler.get_btn_pressed("right") or axis_x > 0.5:
                    world.is_timer_active = True
                    dx = self.speed * dt
                    self.dir = 0
                    self.curr_animation = "Walking"
                else:
                    self.curr_animation = "Idle"
                    self.curr_frame = min(
                        self.curr_frame, len(self.animations["Idle"]) - 1
                    )

                if self.btnhandeler.get_btn_pressed("e") or (
                    self.joystick and self.joystick.get_button(2)
                ):
                    if self.dash_cooldown_timer_time == False:
                        self.dash_active = True

            if self.dash_active and self.dash_cooldown_timer <= 0.0:
                dx = self.speed * dt * 2.5 * (1 if self.dir == 0 else -1)
                self.curr_animation = "Dash"
                self.curr_frame = min(self.curr_frame, len(self.animations["Dash"]) - 1)
                self.dash_timer += dt
                if self.dash_timer >= self.dash_duration:
                    self.dash_active = False
                    self.dash_timer = 0.0
                    self.dash_cooldown_timer_time = True

        if self.dash_cooldown_timer_time:
            self.dash_cooldown_timer += dt
            if self.dash_cooldown_timer >= self.dash_cooldown_time:
                self.dash_cooldown_timer_time = False
                self.dash_cooldown_timer = 0.0

        if self.current_effect == 1:
            dx *= 2.5

        # -- Jump input ----------------------------------------------------
        try:
            self.jump_down = self.btnhandeler.get_btn_pressed("up") or (
                self.joystick and self.joystick.get_button(0)
            )
        except Exception:
            self.jump_down = False

        jump_just_pressed = self.jump_down and not self.freeze_frame_active
        self._prev_jump = self.jump_down

        if jump_just_pressed:
            self.jump_buffer_timer = self.jump_buffer_time
        else:
            self.jump_buffer_timer = max(0.0, self.jump_buffer_timer - dt)

        if self.on_ground:
            self.coyote_timer = self.coyote_time
        else:
            self.coyote_timer = max(0.0, self.coyote_timer - dt)

        # -- Wall jump -----------------------------------------------------
        wall_jumped = False
        if (
            controls_allowed
            and jump_just_pressed
            and not self.on_ground
            and self.wall_jump_dir_lock_timer <= 0.0
        ):
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

        # -- Normal jump ---------------------------------------------------
        if controls_allowed and not wall_jumped:
            if (
                self.jump_buffer_timer > 0.0
                and self.coyote_timer > 0.0
                and not self.is_jumping
            ):
                self.speed_y = (
                    self.jump_speed * 1.3
                    if self.current_effect == 2
                    else self.jump_speed
                )
                self.is_jumping = True
                self.jump_hold_timer = self.max_jump_hold_time
                self.jump_buffer_timer = 0.0
                self.coyote_timer = 0.0

        # ----------------------------------------------------------------
        if not self._cam_catchup_active:
            # -- Gravity -----------------------------------------------
            gravity_jump_hold = 180
            gravity_jump_release = 480
            gravity_fall = 810

            if self.speed_y < 0:
                if self.is_jumping and self.jump_down and self.jump_hold_timer > 0.0:
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
                holding_left = self.btnhandeler.get_btn_pressed("left") or axis_x < -0.5
                holding_right = (
                    self.btnhandeler.get_btn_pressed("right") or axis_x > 0.5
                )
                if (self.touching_wall_left and holding_left) or (
                    self.touching_wall_right and holding_right
                ):
                    self.speed_y = min(self.speed_y, self.wall_slide_max_fall)

            dy = self.speed_y * dt

            # -- Horizontal collision + step-up --------------------------------
            if ignore_collisions:
                self.world_x += dx
            else:
                h_test = pygame.Rect(
                    int(self.world_x + dx + hbx),
                    int(self.world_y + hby),
                    hb.width,
                    hb.height,
                )
                if not check_collision_including_invis(
                    world, h_test, deactivated=deact
                ):
                    self.world_x += dx
                elif dx != 0:
                    for step in range(1, 6):
                        move_test = pygame.Rect(
                            int(self.world_x + dx + hbx),
                            int(self.world_y + hby - step),
                            hb.width,
                            hb.height,
                        )
                        stand_test = pygame.Rect(
                            int(self.world_x + hbx),
                            int(self.world_y + hby - step),
                            hb.width,
                            hb.height,
                        )
                        if not check_collision_including_invis(
                            world, move_test, deactivated=deact
                        ) and not check_collision_including_invis(
                            world, stand_test, deactivated=deact
                        ):
                            self.world_x += dx
                            self.world_y -= step
                            break

            # -- Vertical collision --------------------------------------------
            if ignore_collisions:
                self.world_y += dy
                landed = False
            else:
                pre_move_y = self.world_y
                v_test = pygame.Rect(
                    int(self.world_x + hbx),
                    int(self.world_y + hby + dy),
                    hb.width,
                    hb.height,
                )

                landed = False
                if check_collision_including_invis(world, v_test, deactivated=deact):
                    self.world_y = pre_move_y
                    self.speed_y = 0.0
                    landed = dy > 0
                else:
                    self.world_y += dy

            prev_on_ground = self.on_ground
            self.on_ground = landed

            if self.on_ground and not prev_on_ground:
                self.is_jumping = False
                self.jump_hold_timer = 0.0
                self.coyote_timer = self.coyote_time

            self.update_hitbox()

        # ----------------------------------------------------------------
        # Vertical camera: follow, or freeze + slide-catchup if offscreen
        # ----------------------------------------------------------------
        if not self.dead:
            cam_y_now = getattr(world, "cam_y", 0.0)
            screen_h = screen.get_height()
            half_h = screen_h / 2.0
            player_screen_y = self.world_y - cam_y_now

            if self._cam_catchup_active:
                # Player is fully frozen; ease the camera down to meet them.
                self._cam_catchup_timer += dt
                t = min(self._cam_catchup_timer / self._cam_catchup_dur, 1.0)
                eased_t = self._ease_out_back(t)
                new_cam_y = (
                    self._cam_catchup_start_y
                    + (self._cam_catchup_target_y - self._cam_catchup_start_y) * eased_t
                )
                world.scroll_cam_y(new_cam_y + half_h, speed=None)

                if t >= 1.0:
                    self._cam_catchup_active = False
                    self.frozen = False

            # elif self.camera_y_lock:
            #     # External hard override (cutscenes / triggers)
            #     cam_target = self.camera_y_lock_target
            #     cam_speed = self.camera_y_lock_speed
            #     if cam_speed is None:
            #         world.scroll_cam_y(cam_target)
            #     else:
            #         world.scroll_cam_y(cam_target, speed=cam_speed)
            elif (
                (player_screen_y > screen_h or player_screen_y < 0)
                and (world.cam_y != 0 or player_screen_y > screen_h)
                and world.layer_height != screen_h
                and not self.freeze_frame_active
                and not self.death_walk_active
                and self.collision_enabled
            ):
                if  not (world.cam_y + screen_h) == world.layer_height:
                    self.frozen = True
                self._cam_catchup_active = True
                self._cam_catchup_timer = 0.0
                self._cam_catchup_start_y = cam_y_now
                which_screen_in = round(self.world_y / 180) * 180
                if player_screen_y > screen_h:
                    # fell below screen

                    # Do a check to determine final target_y
                    
                    self._cam_catchup_target_y = which_screen_in
            
                else:
                    # went above screen
                    self._cam_catchup_target_y = which_screen_in - screen_h
            
            else:
                pass

        # -- Re-probe walls after move -------------------------------------
        if not ignore_collisions and not self._cam_catchup_active:
            side_probe_h = max(1, hb.height - self.set_step_height_for_snapping)
            left_probe = pygame.Rect(
                int(self.world_x + hbx - 1), int(self.world_y + hby), 1, side_probe_h
            )
            right_probe = pygame.Rect(
                int(self.world_x + hbx + hb.width),
                int(self.world_y + hby),
                1,
                side_probe_h,
            )
            self.touching_wall_left = (
                not self.on_ground
            ) and check_collision_solid_only(world, left_probe)
            self.touching_wall_right = (
                not self.on_ground
            ) and check_collision_solid_only(world, right_probe)
        else:
            self.touching_wall_left = False
            self.touching_wall_right = False

        # -- Save menu (Z key) ---------------------------------------------
        z_pressed = self.btnhandeler.get_btn_pressed("z")
        z_just_pressed = z_pressed and not self._prev_z
        if (
            z_just_pressed
            and not self.save_menu.visible
            and not self.freeze_frame_active
        ):
            self.save_menu.show()
        self._prev_z = z_pressed

        if self.save_menu.visible and not self.freeze_frame_active:
            self.in_save_menu = True
            action = self.save_menu.handle_input(keys)
            if action == "Save" and not self._saving:
                self._saving = True
            if action is None:
                self._saving = False
            return
        else:
            self.in_save_menu = False

        # -- Triggers ------------------------------------------------------
        if (
            not self.freeze_frame_active
            and not self.death_walk_active
            and not self._cam_catchup_active
        ):
            level_key = f"level_{getattr(world, 'current_level', current_level or 0)}"
            current_level_num = getattr(world, "current_level", current_level or 0)

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

                trect = pygame.Rect(
                    trigger["x"], trigger["y"], trigger["w"], trigger["h"]
                )
                name = trigger.get("name", "").strip()

                if not player_rect.colliderect(trect):
                    continue

                current_collisions.add(trigger_key)

                if trigger_key not in self._in_triggers:
                    self._in_triggers.add(trigger_key)

                    if name == "print":
                        print("Trigger COLLIDE!")
                        self._triggered_once.add(trigger_key)

                    elif name == "kill_player":
                        self.can_move = True
                        self.apply_spawn_point(world.current_level)
                        self._reset_after_respawn()

                    if name == "shadow_platform":
                        for data in world.boxEngine.shadow_data:
                            if data["rect"] == trect:
                                self.current_effect = data["curr_power"]
                                self._shadow_triggers_active.add(trigger_key)

                    if self.active_cutscene and not getattr(
                        self.active_cutscene, "running", False
                    ):
                        self.active_cutscene = None
                    if self.active_interactive and not getattr(
                        self.active_interactive, "running", False
                    ):
                        self.active_interactive = None

                    if name.startswith("cutscene("):
                        cut_id = name[9:-1]
                        if not self.active_cutscene:
                            try:
                                self.incutscene = True
                                self.active_cutscene = (
                                    CutsceneLoaderModule.CutsceneLoader()
                                )
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
                                self.active_interactive = (
                                    InteractableModule.Interactable()
                                )
                                self.curr_animation = "Idle"
                                self.active_interactive.world = world
                                self.active_interactive.event = self.event
                                self.active_interactive.player = self
                                self.active_interactive.load(inter_id, self.joystick)
                                self.active_interactive.trigger_idx = trigger_key
                            except Exception as e:
                                print("Error loading interactable:", e)
                                self.active_interactive = None

                    elif name.startswith("deact_invis("):
                        self._deactivated_walls.add(name[13:-1])
                        self._triggered_once.add(trigger_key)

                    elif name.startswith("goto("):
                        level_target = name[5:-1]
                        print("GO TO LEVEL:", level_target)
                        self.last_level = getattr(world, "current_level", None)
                        world.change_level(level_target, self)
                        self.apply_spawn_point(level_target)
                        if self.active_cutscene:
                            self.active_cutscene = None

                    elif name.startswith("fight("):
                        name = name[6:-1]
                        self.start_encounter(name)

                    elif name.startswith("move_cam_y("):
                        value = name[11:-1]
                        try:
                            self.lock_camera_y(float(value))
                        except Exception:
                            print(f"Bad move_cam_y trigger value: {value}")

            self._in_triggers.intersection_update(current_collisions)

            # -- Shadow trigger exit ---------------------------------------
            shadow_triggers_in_range = set()
            for idx, trigger in enumerate(triggers):
                trigger_id = trigger.get("id")
                trigger_key = trigger_id if trigger_id else f"_idx_{idx}"
                name = trigger.get("name", "").strip()
                if name == "shadow_platform":
                    trect = pygame.Rect(
                        trigger["x"], trigger["y"], trigger["w"], trigger["h"]
                    )
                    if player_rect.colliderect(trect):
                        shadow_triggers_in_range.add(trigger_key)

            exited_shadow = self._shadow_triggers_active - shadow_triggers_in_range
            if exited_shadow:
                self._shadow_triggers_active -= exited_shadow
                if not self._shadow_triggers_active:
                    self.current_effect = None

            # -- Active interactive cleanup --------------------------------
            if self.active_interactive:
                trig = getattr(self.active_interactive, "trigger_idx", None)
                if trig not in self._in_triggers:
                    self.active_interactive = None

            # -- Update active scenes --------------------------------------
            if self.active_cutscene:
                self.active_cutscene.update(dt, self)
            if self.active_interactive:
                self.active_interactive.update(dt)
        else:
            pass  # pause triggers during freeze / death walk / camera catch-up

    # ---------------------------------------------------------------------
    # Draw
    # ---------------------------------------------------------------------

    def _ease_out_back(self, t):
        """Overshoot-bounce easing (t in 0..1)."""
        c1 = 1.70158
        c3 = c1 + 1.0
        return 1.0 + c3 * pow(t - 1.0, 3) + c1 * pow(t - 1.0, 2)

    def _ease_in_quad(self, t):
        return t * t

    def draw(self, screen, world, true_screen):
        self.true_screen = true_screen
        font_large, font_small = self._death_fonts()
        sw, sh = screen.get_size()

        # ----------------------------------------------------------------
        # Death screen
        # ----------------------------------------------------------------
        if self.dead:
            world.Time_left_in_timer_that_times_the_time_in_a_timely_manner = 0.0
            self.dash_timer = 0.0
            self.dash_active = False
            screen.fill((0, 0, 0))
            # Force death animation
            self.curr_animation = "dead"
            if self.curr_animation != self._prev_animation:
                self.curr_frame = 0
                self.animation_timer = 0.0
                self._prev_animation = self.curr_animation
            frames = self.animations.get("dead", [])
            if frames:
                self.animation_timer += self.dt
                while self.animation_timer >= self.animation_speed:
                    self.animation_timer -= self.animation_speed
                    self.curr_frame = min(
                        self.curr_frame + 1, len(frames) - 1
                    )  # clamp, don't loop
                img = frames[self.curr_frame]
                cx = screen.get_width() // 2 - 50 + self.offset_x
                cy = screen.get_height() // 2 + self.offset_y
                screen.blit(
                    img, (cx - img.get_width() // 2, cy - img.get_height() // 2)
                )
            if self.lives <= 0 and not self.in_death_scene:
                try:
                    self.active_cutscene = CutsceneLoaderModule.CutsceneLoader()
                    self.curr_animation = "Idle"
                    self.active_cutscene.world = world
                    self.active_cutscene.event = self.event
                    self.active_cutscene.player = self
                    self.active_cutscene.load("death", self.joystick)
                    self.active_cutscene.trigger_idx = 999999999999999999999999
                    self.in_death_scene = True
                except Exception as e:
                    print("Error loading cutscene:", e)
                    self.active_cutscene = None
            if not font_large:
                return

            phase = self._ds_phase
            t_raw = self._ds_phase_timer
            cx = sw // 2
            cy = sh // 2

            old_lives = self._ds_lives_before
            new_lives = self.lives

            if phase == _DS_FADE_IN:
                return

            if phase == _DS_HOLD:
                return

            if phase == _DS_OLD_OUT:
                t = min(t_raw / self._ds_old_out_dur, 1.0)
                ease_t = self._ease_in_quad(t)

                slide_y = cy - int(ease_t * 12)
                alpha = int(255 * (1.0 - ease_t))

                label = font_large.render(f"   {old_lives}", False, (255, 255, 255))
                Xlabel = font_large.render("X", False, (255, 255, 255))
                surf = pygame.Surface(label.get_size(), pygame.SRCALPHA)
                surf.blit(label, (0, 0))
                screen.blit(
                    Xlabel, (cx - Xlabel.get_width() - 4, cy - Xlabel.get_height() // 2)
                )
                surf.set_alpha(alpha)
                screen.blit(
                    surf,
                    (cx - label.get_width() // 2, slide_y - label.get_height() // 2),
                )

            if phase == _DS_NEW_IN:
                self.offset_x = random.randint(-2, 2)
                self.offset_y = random.randint(-2, 2)

                t = min(t_raw / self._ds_new_in_dur, 1.0)
                ease_t = self._ease_out_back(t)

                start_y = cy + 16
                slide_y = int(start_y + (cy - start_y) * ease_t)
                alpha = min(255, int(255 * (t * 3.0)))

                label = font_large.render(f"   {new_lives}", False, (255, 255, 255))
                Xlabel = font_large.render("X", False, (255, 255, 255))
                surf = pygame.Surface(label.get_size(), pygame.SRCALPHA)
                surf.blit(label, (0, 0))
                screen.blit(
                    Xlabel, (cx - Xlabel.get_width() - 4, cy - Xlabel.get_height() // 2)
                )
                surf.set_alpha(alpha)
                screen.blit(
                    surf,
                    (cx - label.get_width() // 2, slide_y - label.get_height() // 2),
                )

            if phase == _DS_DONE:
                self.offset_x = random.randint(-2, 2)
                self.offset_y = random.randint(-2, 2)

                label = font_large.render(f"   {new_lives}", False, (255, 255, 255))
                Xlabel = font_large.render("X", False, (255, 255, 255))
                screen.blit(
                    Xlabel, (cx - Xlabel.get_width() - 4, cy - Xlabel.get_height() // 2)
                )
                screen.blit(
                    label, (cx - label.get_width() // 2, cy - label.get_height() // 2)
                )

        # ----------------------------------------------------------------
        # Normal player draw
        # ----------------------------------------------------------------
        if self.dead:
            return

        self.offset_x = 0
        self.offset_y = 0
        cam_x = getattr(world, "cam_x", 0)
        cam_y = getattr(world, "cam_y", 0)

        self.rect.size = self.image.get_size()
        draw_rect = self.rect.copy()

        float_center_x = self.world_x + self.hitbox_offset_x + self.hit_box.width / 2.0
        float_bottom_y = self.world_y + self.hitbox_offset_y + self.hit_box.height

        draw_rect.midbottom = (
            round(float_center_x - cam_x),
            round(float_bottom_y - cam_y),
        )
        if self.curr_animation == "imnotracist":
            screen.fill((0, 0, 0))
        try:
            img = self.image_left if self.dir else self.image_right
            screen.blit(img, draw_rect)
        except Exception:
            try:
                screen.blit(self.image, draw_rect)
            except Exception:
                pygame.draw.rect(screen, (0, 255, 0), draw_rect)

        # Draw the cooldown dash thingy
        if self.dash_cooldown_timer_time:
            image = self.animations["Dash_cooldown"][1]

            progress = self.dash_cooldown_timer / self.dash_cooldown_time
            progress = max(0.0, min(progress, 1.0))

            w, h = image.get_size()
            cx, cy = w // 2, h // 2
            radius = min(w, h) // 2

            start_angle = math.radians(90)
            end_angle = start_angle + (2 * math.pi * progress)

            if not hasattr(self, "_cooldown_pixel_mask"):
                m = pygame.mask.from_surface(image)
                self._cooldown_pixel_mask = m.to_surface(
                    setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0)
                )

            pixel_mask = self._cooldown_pixel_mask

            # --- build solid wedge (no feather) ---
            wedge = pygame.Surface((w, h), pygame.SRCALPHA)
            steps = 180
            points = [(cx, cy)]
            for i in range(steps + 1):
                t = i / steps
                angle = start_angle + t * (end_angle - start_angle)
                x = cx + math.cos(angle) * (radius + 1)
                y = cy - math.sin(angle) * (radius + 1)
                points.append((x, y))
            pygame.draw.polygon(wedge, (255, 255, 255, 255), points)

            # --- build alpha mask from wedge + pixel mask ---
            mask = pygame.Surface((w, h), pygame.SRCALPHA)
            mask.blit(wedge, (0, 0))
            mask.blit(pixel_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

            # --- apply ONLY alpha channel to result, leave RGB untouched ---
            result = image.copy().convert_alpha()
            alpha_arr = pygame.surfarray.pixels_alpha(result)
            mask_arr = pygame.surfarray.pixels_alpha(mask)
            alpha_arr[:] = mask_arr
            del alpha_arr, mask_arr

            screen.blit(
                self.animations["Dash_cooldown"][0],
                result.get_rect(x=draw_rect.x + 20, y=draw_rect.y - 10),
            )
            screen.blit(result, result.get_rect(x=draw_rect.x + 20, y=draw_rect.y - 10))

        if self.show_encounter:
            screen.blit(self.encounter_image, (draw_rect.x + 10, draw_rect.y - 10))

        if self.save_menu.visible:
            try:
                self.save_menu.draw(screen)
            except Exception:
                pass

        self.midgamemenu.draw(screen, true_screen)
