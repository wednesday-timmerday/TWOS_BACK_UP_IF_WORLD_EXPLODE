from PIL import Image

input_path = "worlds/3/2.png"
output_path = "worlds/3/2.png"

img = Image.open(input_path)

target_height = 180
width, height = img.size
target_width = round(width * (target_height / height))

# Pixel-perfect scaling
resized = img.resize((target_width, target_height), Image.Resampling.NEAREST)

resized.save(output_path)

print(f"Nieuwe grootte: {target_width}x{target_height}")