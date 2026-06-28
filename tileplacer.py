import json
import os
import xml.etree.ElementTree as ET

from PIL import Image


MAP_FILE = "nohito.tmj"


def load_tsx(tsx_path):
    tree = ET.parse(tsx_path)
    root = tree.getroot()

    tile_width = int(root.attrib["tilewidth"])
    tile_height = int(root.attrib["tileheight"])

    image = root.find("image")

    image_source = image.attrib["source"]
    image_width = int(image.attrib["width"])
    image_height = int(image.attrib["height"])

    return {
        "tile_width": tile_width,
        "tile_height": tile_height,
        "image_source": image_source,
        "image_width": image_width,
        "image_height": image_height,
    }


def slice_tiles(tileset_image, tile_width, tile_height):
    tiles = {}

    cols = tileset_image.width // tile_width
    rows = tileset_image.height // tile_height

    gid = 1

    for y in range(rows):
        for x in range(cols):
            tile = tileset_image.crop(
                (
                    x * tile_width,
                    y * tile_height,
                    (x + 1) * tile_width,
                    (y + 1) * tile_height,
                )
            )

            tiles[gid] = tile
            gid += 1

    return tiles


def main():
    with open(MAP_FILE, "r", encoding="utf-8") as f:
        map_data = json.load(f)

    map_dir = os.path.dirname(os.path.abspath(MAP_FILE))

    tileset_ref = map_data["tilesets"][0]
    first_gid = tileset_ref["firstgid"]

    tsx_path = os.path.join(map_dir, tileset_ref["source"])

    tsx = load_tsx(tsx_path)

    tileset_image_path = os.path.join(
        os.path.dirname(tsx_path),
        tsx["image_source"]
    )

    tileset_image = Image.open(tileset_image_path).convert("RGBA")

    tiles = slice_tiles(
        tileset_image,
        tsx["tile_width"],
        tsx["tile_height"]
    )

    map_width = map_data["width"]
    map_height = map_data["height"]

    output_width = map_width * tsx["tile_width"]
    output_height = map_height * tsx["tile_height"]

    for layer in map_data["layers"]:
        if layer["type"] != "tilelayer":
            continue

        layer_image = Image.new(
            "RGBA",
            (output_width, output_height),
            (0, 0, 0, 0)
        )

        data = layer["data"]

        for index, gid in enumerate(data):
            if gid == 0:
                continue

            local_gid = gid - first_gid + 1

            tile = tiles.get(local_gid)

            if tile is None:
                continue

            x = index % map_width
            y = index // map_width

            layer_image.paste(
                tile,
                (
                    x * tsx["tile_width"],
                    y * tsx["tile_height"],
                ),
            )

        filename = f"{layer['name']}.png"

        layer_image.save(filename)

        print("Saved:", filename)


if __name__ == "__main__":
    main()