from PIL import Image
import random
import math

# ===== SETTINGS =====
BACKGROUND_PATH = "ui/menu/bg_image_2.png"
STAR1_PATH = "ui/menu/star_1.png"
STAR2_PATH = "ui/menu/star_2.png"
OUTPUT_PATH = "result.png"

NUM_STARS = 120
MAX_ATTEMPTS = 100

STAR1_WEIGHT = 0.6
STAR2_WEIGHT = 0.4

# Extra padding between stars (in pixels)
STAR_PADDING = 8
# ====================


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


# Load images
bg = Image.open(BACKGROUND_PATH).convert("RGBA")
star1 = Image.open(STAR1_PATH).convert("RGBA")
star2 = Image.open(STAR2_PATH).convert("RGBA")

width, height = bg.size

result = bg.copy()
placed_stars = []

for _ in range(NUM_STARS):
    placed = False

    for _ in range(MAX_ATTEMPTS):
        # Pick a star type
        star = random.choices(
            [star1, star2],
            weights=[STAR1_WEIGHT, STAR2_WEIGHT]
        )[0]

        sw, sh = star.size

        # Make sure the star fits
        if sw >= width or sh >= height:
            continue

        # Random position
        x = random.randint(0, width - sw)
        y = random.randint(0, height - sh)

        center = (x + sw / 2, y + sh / 2)
        radius = max(sw, sh) / 2

        valid = True

        for existing_center, existing_radius in placed_stars:
            min_dist = radius + existing_radius + STAR_PADDING

            if distance(center, existing_center) < min_dist:
                valid = False
                break

        if valid:
            result.alpha_composite(star, (x, y))
            placed_stars.append((center, radius))
            placed = True
            break

    if not placed:
        print("Warning: Couldn't place a star.")

result.save(OUTPUT_PATH)
print(f"Saved to {OUTPUT_PATH}")