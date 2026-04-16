import pygame
import numpy as np
import cv2

# Initialiseer pygame
pygame.init()

# Scherm instellingen
WIDTH, HEIGHT = 1280, 720
PIXEL_SIZE = 6

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("TV Sneeuw + Recording")

clock = pygame.time.Clock()

# Video writer (MP4)
fourcc = cv2.VideoWriter_fourcc(*"mp4v")
out = cv2.VideoWriter("tv_static.mp4", fourcc, 60.0, (WIDTH, HEIGHT))

# Kleine surface voor chunky pixels
small_w, small_h = WIDTH // PIXEL_SIZE, HEIGHT // PIXEL_SIZE
small_surface = pygame.Surface((small_w, small_h))

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    # Noise genereren
    noise = np.random.randint(0, 256, (small_w, small_h), dtype=np.uint8)
    noise_rgb = np.stack((noise, noise, noise), axis=-1)

    pygame.surfarray.blit_array(small_surface, noise_rgb)

    # Opschalen
    scaled = pygame.transform.scale(small_surface, (WIDTH, HEIGHT))
    screen.blit(scaled, (0, 0))

    pygame.display.flip()

    # Frame capturen en naar video schrijven
    frame = pygame.surfarray.array3d(screen)
    frame = np.transpose(frame, (1, 0, 2))  # fix orientatie
    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    out.write(frame)

    clock.tick(60)

# Opruimen
out.release()
pygame.quit()