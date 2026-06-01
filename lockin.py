import pygame
import cv2
import platform

pygame.init()
screen = pygame.display.set_mode((640, 480))
pygame.display.set_caption("BOOTING CAMERA...")
clock = pygame.time.Clock()

# Pick the fastest backend for your OS
if platform.system() == "Windows":
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
elif platform.system() == "Linux":
    cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
else:
    cap = cv2.VideoCapture(0)  # macOS — no faster backend available

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
cap.set(cv2.CAP_PROP_FPS, 30)  # Lock FPS early — avoids negotiation lag

# 2 warmup frames is enough
for _ in range(2):
    cap.read()

pygame.display.set_caption("Camera Feed")

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    ret, frame = cap.read()
    if not ret:
        continue

    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    surface = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
    screen.blit(surface, (0, 0))
    pygame.display.flip()
    clock.tick(30)

cap.release()
pygame.quit()