from PIL import Image



image_path = f"thingy_2.png"
image = Image.open(image_path)

# Convert image to RGBA (to handle transparency) if not already
image = image.convert("RGBA")

# Get the bounding box of the non-blank areas
bbox = image.getbbox()
cropped_image = image.crop(Image.open(image_path).convert("RGBA").getbbox())

# Save the cropped image
cropped_image.save(image_path)
print("Image cropped and saved as sprites/blobtigoo/blobtigoo-1_cropped.png")