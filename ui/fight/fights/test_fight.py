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
    fight_instance.text_engine.start_text("* This feels wrong^wait1000& & & & &and incomplete", "shadowrock")
    fight_instance.bullet_timer = 0
    fight_instance.bullet_interval = 1.0  # seconds

def run(fight_instance, dt, joystick):

    if not fight_instance.text_engine.finished:
        fight_instance.text_engine.update(dt)
        return

    # Monster turn
    if fight_instance.current_turn == 1:

        fight_instance.bullet_timer += dt

        if fight_instance.bullet_timer >= fight_instance.bullet_interval:
            fight_instance.bullet_timer = 0

            center_x = 1066 / 2
            center_y = 280 + 150  # center of attack box

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
