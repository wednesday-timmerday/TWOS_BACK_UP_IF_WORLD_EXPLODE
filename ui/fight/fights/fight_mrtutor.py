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

import pygame 

import random

atk_index = 0
balk_spawned = False
balk_spawned = False

def init(fight_instance):
    fight_instance.monster_path = fight_instance.monster_loader.load("btn_e/frames/btn_e-1.png") #AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA TODO REplace this very noice placeholder E btn ARothfdiuph
    fight_instance.monster_image = pygame.image.load(fight_instance.monster_path).convert_alpha()
    fight_instance.monster_def = 20 #idfk
    fight_instance.monster_atk = 15
    fight_instance.monster_hp = 120
    fight_instance.monster_max_hp = 120
    fight_instance.fight_identifier = "mrtutor"
    fight_instance.current_section = 1
    fight_instance.bullet_timer = 0
    fight_instance.turn_timer = 0
    fight_instance.turn_duration = 15.0  # How long the monster's turn lasts
    fight_instance.text_finished_last_frame = False
    fight_instance.bullet_interval = 0.5  # seconds between bullet waves
    fight_instance.hammer_timer = 0  # Track warning/spawn cycles for attack 2
    fight_instance.bullet_engine.register_btype("Balk", fight_instance.monster_loader.load("mrtutor/balk.png"), rotate_to_vel=True)
    fight_instance.bullet_engine.register_btype("hammer", fight_instance.monster_loader.load("hammer/frames/hammer-1.png"), rotate_to_vel=True)


def run(fight_instance, dt, joystick):
    global balk_spawned, atk_index

    # Always update text engine
    if not fight_instance.text_engine.finished:
        fight_instance.text_engine.update(dt)
        fight_instance.text_finished_last_frame = False

        # Only block progression if IN_BBOX (player turn text)
        if fight_instance.bbox:
            return

    else:
        fight_instance.text_finished_last_frame = True

    # Monster turn

    if fight_instance.current_turn == 1:

        fight_instance.turn_timer += dt
        fight_instance.bullet_timer += dt
        
        #I sense an if/else hell incoming

        if atk_index == 0:
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
            cycle_duration = 1.5  # 1 sec warning + 0.5 sec cooldown
            time_in_cycle = fight_instance.hammer_timer % cycle_duration
            current_cycle = int(fight_instance.hammer_timer / cycle_duration)
            
            if time_in_cycle < 1.0:
                # Warning phase - add warning once per cycle
                if current_cycle > getattr(fight_instance, 'last_hammer_cycle', -1):
                    warning_x = random.randint(460, 820)
                    hammer_w = 75 * 2  # match hammer bullet size (radius -> diameter)
                    fight_instance.bullet_engine.add_warning(
                        x=warning_x - hammer_w // 2,
                        y=336,
                        size=hammer_w,
                        time_out=1.0
                    )
                    fight_instance.last_hammer_cycle = current_cycle
                    fight_instance.pending_hammer_x = warning_x
            else:
                # Drop hammer after warning expires (0.5 sec cooldown window)
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
            
            # Reset drop flag at start of new cycle
            if time_in_cycle < 0.05:
                fight_instance.hammer_dropped_this_cycle = False
        # End monster's turn after duration expires
        if fight_instance.turn_timer >= fight_instance.turn_duration:
            fight_instance.turn_timer = 0
            fight_instance.bullet_timer = 0
            fight_instance.hammer_timer = 0
            fight_instance.current_turn = 0  # Switch back to player's turn
            fight_instance.bullet_engine.clear()  # Clear bullets for next round
            fight_instance.current_section += 1
            fight_instance.load_section_text()
            balk_spawned = False
            atk_index += 1