import os
import pygame

# ---------------- CONFIG ----------------
SOURCE_FOLDER = "worlds/3"
OUTPUT_FOLDER = "worlds/3_chunks"
CHUNK_WIDTH = 100  # Width of each chunk
TARGET_HEIGHT = 600
# ----------------------------------------

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

pygame.init()
screen = pygame.display.set_mode((1, 1))  # Minimal display for image ops

for filename in os.listdir(SOURCE_FOLDER):
    if not filename.lower().endswith((".png", ".jpg")):
        continue

    src_path = os.path.join(SOURCE_FOLDER, filename)
    img = pygame.image.load(src_path).convert_alpha()

    # --- Resize to target height, keep aspect ratio ---
    scale_factor = TARGET_HEIGHT / img.get_height()
    new_width = int(img.get_width() * scale_factor)
    new_height = TARGET_HEIGHT
    resized_img = pygame.transform.scale(img, (new_width, new_height))

    # --- Chop into chunks ---
    num_chunks = (new_width + CHUNK_WIDTH - 1) // CHUNK_WIDTH
    for i in range(num_chunks):
        chunk_rect = pygame.Rect(i * CHUNK_WIDTH, 0, CHUNK_WIDTH, new_height)
        chunk_surf = pygame.Surface(chunk_rect.size, pygame.SRCALPHA)
        chunk_surf.blit(resized_img, (0, 0), chunk_rect)

        chunk_name = f"{filename[:-4]}_chunk_{i}.png"
        out_path = os.path.join(OUTPUT_FOLDER, chunk_name)
        pygame.image.save(chunk_surf, out_path)
        print(f"Saved {chunk_name} ({chunk_rect.size})")

pygame.quit()
print("All layers resized and chopped into chunks!")
