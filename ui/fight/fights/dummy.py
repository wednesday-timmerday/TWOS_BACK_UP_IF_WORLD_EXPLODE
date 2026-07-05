""""
This fight would have:
1. A attack with just random bullets going sidewards?
2. An "tube" that just rotates around its own axis
3. Hammers falling
4. Hats teleporting in and exploding
5. Oil (a like miku miku beaaam of oil that sweeps the Bbox)
6. Tutor like searches in his toolbox. (he grabs like hammers or smth idfk)
7. He throws the toolbox, on impact exploding
"""

#TODO: Move textengine stuff to fight.py... and fix self.render_text_bbox

import pygame 
import cutscenes.loader as CutsceneLoaderModule
import random
from assetsLoader import Loader

music_loader = Loader("music")

music_path = music_loader.load("hi.ogg")

pygame.mixer.music.load(music_path)

pygame.mixer.music.play(-1)

atk_index = True
balk_spawned = False

def init(fight_instance):
    fight_instance.monster_path = fight_instance.monster_loader.load("btn_e/frames/btn_e-1.png")
    fight_instance.monster_image = pygame.image.load(fight_instance.monster_path).convert_alpha()
    fight_instance.monster_def = 15
    fight_instance.monster_atk = 15
    fight_instance.monster_hp = 20
    fight_instance.monster_max_hp = 20
    fight_instance.fight_identifier = "dummy"
    fight_instance.current_section = 1
    fight_instance.bullet_timer = 0
    fight_instance.turn_timer = 0
    fight_instance.turn_duration = 15.0
    fight_instance.text_finished_last_frame = False
    fight_instance.bullet_interval = 0.5
    fight_instance.hammer_timer = 0
    fight_instance.hat_timer = 0
    fight_instance.bullet_engine.register_btype("Balk", fight_instance.monster_loader.load("mrtutor/balk.png"), rotate_to_vel=True)
    fight_instance.bullet_engine.register_btype("hammer", fight_instance.monster_loader.load("hammer/frames/hammer-1.png"), rotate_to_vel=True)
    fight_instance.hat_exploded_this_cycle = True
    fight_instance.section_advanced_this_turn = False


def run(fight_instance, dt, joystick):
    global balk_spawned, atk_index

    # Always update text engine
    if not fight_instance.text_engine.finished:
        fight_instance.text_engine.update(dt)
        fight_instance.text_finished_last_frame = False

        if fight_instance.bbox:
            return

    else:
        fight_instance.text_finished_last_frame = True

    # Monster turn
    if fight_instance.current_turn == 1:

        # Advance section once per turn
        if not fight_instance.section_advanced_this_turn:
            fight_instance.current_section += 1
            fight_instance.section_advanced_this_turn = True

        fight_instance.turn_timer += dt
        fight_instance.bullet_timer += dt
        
        if atk_index:
            fight_instance.turn_timer += dt
            fight_instance.bullet_timer += dt

            if fight_instance.bullet_timer >= fight_instance.bullet_interval:
                fight_instance.bullet_timer = 0
                bullet_count = 1

                for i in range(bullet_count):
                    fight_instance.spawn_bullet(
                        x=random.randint(60, 400),
                        y=random.randint(84*4, 174*4),
                        size=6,
                        color=(255, 0, 0),
                        damage=5,
                        rotation=0,
                        speed=200,
                        type="dot"
                    )

        elif atk_index == 1:
            if not balk_spawned:
                balk_spawned = True
                fight_instance.spawn_bullet(
                    x=640,
                    y=516,
                    size=200,
                    color=(255, 0, 0),
                    damage=7,
                    rotation=0,
                    speed=0,
                    type="Balk",
                    angular_velocity=120.0
                )

        elif atk_index == 2:
            fight_instance.hammer_timer += dt
            cycle_duration = 1.5
            time_in_cycle = fight_instance.hammer_timer % cycle_duration
            current_cycle = int(fight_instance.hammer_timer / cycle_duration)
            
            if time_in_cycle < 1.0:
                if current_cycle > getattr(fight_instance, 'last_hammer_cycle', -1):
                    warning_x = random.randint(460, 820)
                    hammer_w = 75 * 2
                    fight_instance.bullet_engine.add_warning(
                        x=warning_x - hammer_w // 2,
                        y=336,
                        size=hammer_w,
                        time_out=1.0
                    )
                    fight_instance.last_hammer_cycle = current_cycle
                    fight_instance.pending_hammer_x = warning_x
            else:
                if hasattr(fight_instance, 'pending_hammer_x') and not getattr(fight_instance, 'hammer_dropped_this_cycle', False):
                    fight_instance.spawn_bullet(
                        x=fight_instance.pending_hammer_x,
                        y=336,
                        size=75,
                        damage=20,
                        rotation=90,
                        speed=2000,
                        type="hammer",
                        color=(255,0,0)
                    )
                    fight_instance.hammer_dropped_this_cycle = True
            
            if time_in_cycle < 0.05:
                fight_instance.hammer_dropped_this_cycle = False

        elif atk_index == 3:
            fight_instance.hat_timer += dt
            cycle_duration = 1.0
            time_in_cycle = fight_instance.hat_timer % cycle_duration
            current_cycle = int(fight_instance.hat_timer / cycle_duration)
            
            if time_in_cycle < 0.7:
                if current_cycle > getattr(fight_instance, 'last_hat_cycle', -1) and getattr(fight_instance, 'hat_exploded_this_cycle', False):
                    hat_x = random.randint(480, 800)
                    hat_y = random.randint(336, 336+90*4)
                    hat_bullet_id = fight_instance.spawn_bullet(
                        x=hat_x,
                        y=hat_y,
                        size=40,
                        damage=0,
                        rotation=0,
                        speed=0,
                        type="dot",
                        color=(180, 100, 50)
                    )
                    fight_instance.last_hat_cycle = current_cycle
                    fight_instance.pending_hat_x = hat_x
                    fight_instance.pending_hat_y = hat_y
                    fight_instance.pending_hat_id = hat_bullet_id
                    fight_instance.hat_exploded_this_cycle = False
            else:
                if hasattr(fight_instance, 'pending_hat_x') and not getattr(fight_instance, 'hat_exploded_this_cycle', False):
                    if hasattr(fight_instance, 'pending_hat_id') and fight_instance.pending_hat_id is not None:
                        try:
                            fight_instance.bullet_engine._deactivate(fight_instance.pending_hat_id)
                        except Exception:
                            pass
                    
                    Explosion_id = fight_instance.spawn_bullet(
                        x=fight_instance.pending_hat_x,
                        y=fight_instance.pending_hat_y,
                        size=60,
                        damage=15,
                        rotation=0,
                        speed=0,
                        type="dot",
                        color=(255, 150, 0)
                    )
                    fight_instance.pending_exp_id = Explosion_id
                    if time_in_cycle >= 0.9:
                        try:
                            fight_instance.bullet_engine._deactivate(fight_instance.pending_exp_id)
                        except Exception:
                            pass
                        fight_instance.hat_exploded_this_cycle = True
                        print("Dance")

        # End monster's turn after duration expires
        if fight_instance.turn_timer >= fight_instance.turn_duration:
            fight_instance.turn_timer = 0
            fight_instance.bullet_timer = 0
            fight_instance.hammer_timer = 0
            fight_instance.hat_timer = 0
            fight_instance.section_advanced_this_turn = False  # reset for next turn
            fight_instance.current_turn = 0
            fight_instance.bullet_engine.clear()
            fight_instance.load_section_text()
            balk_spawned = False
            atk_index += 1


def killed(fight_instance, dt, joystick):
    fight_instance.player.incutscene = True
    fight_instance.player.active_cutscene = CutsceneLoaderModule.CutsceneLoader()
    fight_instance.player.curr_animation = "Idle"
    fight_instance.player.active_cutscene.world = fight_instance.player.world
    fight_instance.player.active_cutscene.event = fight_instance.player.event
    fight_instance.player.active_cutscene.player = fight_instance.player
    fight_instance.player.active_cutscene.load("tutor_r8_killed_dummy", joystick)
    fight_instance.player.active_cutscene.trigger_idx = 999999
    return 1

def spared(fight_instance, dt, joystick):
    pass