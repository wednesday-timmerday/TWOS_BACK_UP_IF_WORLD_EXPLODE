from PIL import Image

img = Image.open("input.jpg")

# 1. real grayscale (NOT binary)
img = img.convert("L")

# 2. pixelation (down + up)
scale = 0.1  # adjust this
small = img.resize(
    (int(img.width * scale), int(img.height * scale)),
    Image.NEAREST
)

pixelated = small.resize(img.size, Image.NEAREST)

pixelated.save("output.png")