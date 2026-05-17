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
    fight_instance.bullet_engine.register_btype("Balk", fight_instance.monster_loader.load("mrtutor/balk.png"), rotate_to_vel=True)
    fight_instance.bullet_engine.register_btype("hammer", fight_instance.monster_loader.load("hammer/frames/hammer-1.png"), rotate_to_vel=True)
    fight_instance.bullet_engine.add_warning(600,84*4,50,True,7)


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
                    size=75, #200
                    color=(255, 0, 0),
                    damage=5,
                    rotation=0,
                    speed=0,
                    type="hammer",
                    angular_velocity=120.0
                )
        # End monster's turn after duration expires
        if fight_instance.turn_timer >= fight_instance.turn_duration:
            fight_instance.turn_timer = 0
            fight_instance.bullet_timer = 0
            fight_instance.current_turn = 0  # Switch back to player's turn
            fight_instance.bullet_engine.clear()  # Clear bullets for next round
            fight_instance.current_section += 1
            fight_instance.load_section_text()
            balk_spawned = False
            atk_index += 1