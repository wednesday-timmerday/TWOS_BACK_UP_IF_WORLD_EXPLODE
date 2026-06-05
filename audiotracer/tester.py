import pygame
from tracer import AudioTracer

pygame.init()

screen = pygame.display.set_mode((1280, 720))
pygame.display.set_caption("birb")

clock = pygame.time.Clock()
tracer = AudioTracer(screen)

running = True

last_fps = -1

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    tracer.rays = []

    mx, my = pygame.mouse.get_pos()

    for i in range(361):
        tracer.shoot_single_ray(mx, my, i)

    tracer.draw()

    pygame.display.flip()

    clock.tick(60)

    fps = int(clock.get_fps())

    if fps != last_fps:
        print("FPS:", fps)
        last_fps = fps

pygame.quit()