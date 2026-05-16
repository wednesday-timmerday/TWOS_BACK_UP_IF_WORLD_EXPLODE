import pygame



def init(fight_instance):

    # Example initialization logic

    fight_instance.monster_path = fight_instance.monster_loader.load("shadowrock/frames/face_angry.png")

    fight_instance.monster_image = pygame.image.load(fight_instance.monster_path).convert_alpha()

    print(fight_instance.monster_path)



    fight_instance.monster_def = 5

    fight_instance.monster_atk = 10

    fight_instance.monster_hp = 50

    fight_instance.monster_max_hp = 50

    fight_instance.fight_identifier = "test"

    fight_instance.current_section = 1

    fight_instance.bullet_timer = 0

    fight_instance.bullet_interval = 0.3  # seconds between bullet waves
    fight_instance.turn_timer = 0
    fight_instance.turn_duration = 3.0  # How long the monster's turn lasts
    fight_instance.text_finished_last_frame = False



def run(fight_instance, dt, joystick):



    if not fight_instance.text_engine.finished:

        fight_instance.text_engine.update(dt)
        fight_instance.text_finished_last_frame = False

        return
    
    fight_instance.text_finished_last_frame = True



    # Monster turn

    if fight_instance.current_turn == 1:

        fight_instance.turn_timer += dt
        fight_instance.bullet_timer += dt

        if fight_instance.bullet_timer >= fight_instance.bullet_interval:

            fight_instance.bullet_timer = 0

            center_x = 640  # center of screen

            center_y = 360  # center of attack box

            bullet_count = 12

            for i in range(bullet_count):

                angle = (360 / bullet_count) * i

                fight_instance.spawn_bullet(

                    x=center_x,

                    y=center_y,

                    size=6,

                    color=(255, 0, 0),

                    damage=5,

                    rotation=angle,

                    speed=200

                )

        # End monster's turn after duration expires
        if fight_instance.turn_timer >= fight_instance.turn_duration:
            fight_instance.turn_timer = 0
            fight_instance.bullet_timer = 0
            fight_instance.current_turn = 0  # Switch back to player's turn
            fight_instance.bullet_engine.clear()  # Clear bullets for next round
            fight_instance.current_section += 1



