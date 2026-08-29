from PIL import Image

img = Image.open("sprites/Player/animation_frames/lebreah/Idle/Idle_1.png")

rotated = img.rotate(-90, expand=True)

rotated.save("sprites/Player/animation_frames/lebreah/sleep/sleep_1.png")
