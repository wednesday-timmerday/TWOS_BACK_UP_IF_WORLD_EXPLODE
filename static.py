import numpy as np
from PIL import Image
import trimesh

INPUT = "sprites/Player/animation_frames/Idle/Idle_1.png"
OUTPUT = "sprite.glb"
DEPTH = 3

img = Image.open(INPUT).convert("RGBA")
pix = np.array(img)

h, w = pix.shape[:2]
alpha = pix[:, :, 3]
solid = alpha > 0

used = np.zeros((h, w), dtype=bool)

vertices = []
faces = []
uvs = []

def add_quad(v0, v1, v2, v3, uv0, uv1, uv2, uv3):
    i = len(vertices)
    vertices.extend([v0, v1, v2, v3])
    uvs.extend([uv0, uv1, uv2, uv3])
    faces.append([i, i+1, i+2])
    faces.append([i, i+2, i+3])

# 💥 PIXEL-PERFECT LOOP
for y in range(h):
    for x in range(w):

        if used[y, x] or not solid[y, x]:
            continue

        used[y, x] = True

        col = pix[y, x]

        # pixel bounds (1:1, NO MERGING)
        x0, x1 = x, x + 1
        y0, y1 = h - (y + 1), h - y
        z0, z1 = 0, DEPTH

        # UVs = exact texel mapping
        u0 = x / w
        u1 = (x + 1) / w
        v0 = 1 - (y + 1) / h
        v1 = 1 - y / h

        # FRONT FACE
        add_quad(
            (x0, y0, z1),
            (x1, y0, z1),
            (x1, y1, z1),
            (x0, y1, z1),
            (u0, v0),
            (u1, v0),
            (u1, v1),
            (u0, v1),
        )

        # BACK FACE
        add_quad(
            (x1, y0, z0),
            (x0, y0, z0),
            (x0, y1, z0),
            (x1, y1, z0),
            (u1, v0),
            (u0, v0),
            (u0, v1),
            (u1, v1),
        )

        # SIDES (flat color fallback, optional visual depth)
        r, g, b, a = col
        color_uv = (u0, v0)

        # left
        add_quad(
            (x0, y0, z0), (x0, y0, z1),
            (x0, y1, z1), (x0, y1, z0),
            color_uv, color_uv, color_uv, color_uv
        )

        # right
        add_quad(
            (x1, y0, z1), (x1, y0, z0),
            (x1, y1, z0), (x1, y1, z1),
            color_uv, color_uv, color_uv, color_uv
        )

        # bottom
        add_quad(
            (x0, y0, z0), (x1, y0, z0),
            (x1, y0, z1), (x0, y0, z1),
            color_uv, color_uv, color_uv, color_uv
        )

        # top
        add_quad(
            (x0, y1, z1), (x1, y1, z1),
            (x1, y1, z0), (x0, y1, z0),
            color_uv, color_uv, color_uv, color_uv
        )

# build mesh
mesh = trimesh.Trimesh(
    vertices=np.array(vertices),
    faces=np.array(faces),
    process=False
)

mesh.visual.uv = np.array(uvs)
mesh.visual.material = trimesh.visual.texture.SimpleMaterial(image=img)

mesh.export(OUTPUT)

print("saved:", OUTPUT)