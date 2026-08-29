import pygame

import ui.boxEngine.boxengine

#! A simple thing to test/develop a scale system

pygame.init()

SCREEN_RES = (1280, 720)

screen = pygame.display.set_mode(SCREEN_RES)

pygame.display.set_caption("Le test")

running = True

box = (200, 200, 600, 400)


boxengine = ui.boxEngine.boxengine.BoxEngine()
boxengine.create_box(box)


while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    screen.fill((255,255,255))
    #! Shit to render
    try:
        box = (200, 200, pygame.mouse.get_pos()[0], pygame.mouse.get_pos()[1])
        boxengine.create_box(box)
    except Exception:
        pass

    print(pygame.mouse.get_pos())
    boxengine.draw(screen)
    pygame.display.flip()
