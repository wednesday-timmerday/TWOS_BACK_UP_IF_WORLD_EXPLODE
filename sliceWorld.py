import os
import pygame
import math

pygame.init()
pygame.display.set_mode((1,1))  # Nodig om afbeeldingen te laden zonder een echt venster te openen

# ---------- CONFIG ----------
WORLD_FOLDER = "worlds/1_original"      # level folder
LAYER_FILES = ["0.png","1.png","2.png","3.png","4.png"]  # originele lagen
CHUNK_WIDTH = 100             # breedte van 1 chunk
SCREEN_HEIGHT = 600            # hoogte om naar te schalen
# ----------------------------

def slice_layer(layer_path, level_folder, layer_index):
    # laad originele layer
    img = pygame.image.load(layer_path).convert_alpha()

    # schaal naar schermhoogte
    scale_factor = SCREEN_HEIGHT / img.get_height()
    new_w = int(img.get_width() * scale_factor)
    new_h = SCREEN_HEIGHT
    img_scaled = pygame.transform.scale(img, (new_w, new_h))

    # bepaal aantal chunks
    chunk_count = math.ceil(new_w / CHUNK_WIDTH)

    # maak layer folder aan

    for i in range(chunk_count):
        x = i * CHUNK_WIDTH
        w = min(CHUNK_WIDTH, new_w - x)
        chunk_surf = pygame.Surface((w, SCREEN_HEIGHT), pygame.SRCALPHA)
        chunk_surf.blit(img_scaled, (0,0), (x, 0, w, SCREEN_HEIGHT))

        chunk_path = os.path.join(f"worlds/1_chunks", f"{layer_index}_chunk_{i+1}.png")
        pygame.image.save(chunk_surf, chunk_path)
        print(f"[SPLICER] Saved {chunk_path}")

def main():
    for layer_index, file in enumerate(LAYER_FILES):
        layer_path = os.path.join(WORLD_FOLDER, file)
        if not os.path.exists(layer_path):
            print(f"Layer file not found: {layer_path}")
            continue
        slice_layer(layer_path, WORLD_FOLDER, layer_index)

if __name__ == "__main__":
    main()

