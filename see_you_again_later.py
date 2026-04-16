import pygame
import math
import pywavefront
import numpy as np

pygame.init()
WIDTH, HEIGHT = 1066, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()

# --- Camera settings ---
cam_x, cam_y, cam_z = 0, 16, 10
pitch = math.radians(-65)
fov = 90
f = 1 / math.tan(math.radians(fov / 2))

# --- Player settings ---
player_x, player_z = 0.0, 0.0
speed = 0.1

# --- Plane setup ---
plane_size = 10
plane_points = [
    (-plane_size, 0, -plane_size),
    ( plane_size, 0, -plane_size),
    ( plane_size, 0,  plane_size),
    (-plane_size, 0,  plane_size),
]
plane_edges = [(0, 1), (1, 2), (2, 3), (3, 0)]

# --- Load OBJ bullet ---
scene = pywavefront.Wavefront('bullet.obj', collect_faces=True)
vertices = np.array(scene.vertices, dtype=np.float32)

# --- Normalize OBJ ---
min_v = vertices.min(axis=0)
max_v = vertices.max(axis=0)
center = (min_v + max_v) / 2
size = max(max_v - min_v)
vertices = (vertices - center) / size  # [-0.5, 0.5]

print(f"Model normalized. Center was: {center}, size was: {size}")
print(f"Normalized Y range: {vertices[:,1].min():.3f} to {vertices[:,1].max():.3f}")

# --- Pre-collect ALL faces across all meshes once ---
all_faces = []
for mesh in scene.mesh_list:
    all_faces.extend(mesh.faces)
all_faces = np.array(all_faces, dtype=np.int32)  # shape (N, 3)

# --- Bullet settings ---
bullet_angle = 0.0
scale_factor = 5.0
bullet_y = scale_factor * 0.5 + 0.5
bullet_pos = np.array([0.0, bullet_y, 0.0], dtype=np.float32)

# --- Precompute pitch trig ---
cos_p = math.cos(pitch)
sin_p = math.sin(pitch)

def project_batch(verts):
    x = verts[:, 0] - cam_x
    y = verts[:, 1] - cam_y
    z = verts[:, 2] - cam_z

    y2 =  y * cos_p + z * sin_p
    z2 = -y * sin_p + z * cos_p

    valid = z2 < -0.1
    safe_z2 = np.where(valid, z2, -1.0)

    x_proj = (x * f) / -safe_z2
    y_proj = (y2 * f) / -safe_z2

    sx = np.where(valid, (x_proj + 1) * WIDTH / 2,  np.nan)
    sy = np.where(valid, (1 - y_proj) * HEIGHT / 2, np.nan)

    return np.stack([sx, sy], axis=1)

def project(px, py, pz):
    x, y, z = px - cam_x, py - cam_y, pz - cam_z
    y2 =  y * cos_p + z * sin_p
    z2 = -y * sin_p + z * cos_p
    if z2 >= -0.1:
        return None
    x_proj = (x * f) / -z2
    y_proj = (y2 * f) / -z2
    return (int((x_proj + 1) * WIDTH / 2), int((1 - y_proj) * HEIGHT / 2))

running = True
while running:
    screen.fill((0, 0, 0))

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    keys = pygame.key.get_pressed()
    if keys[pygame.K_w]: player_z -= speed
    if keys[pygame.K_s]: player_z += speed
    if keys[pygame.K_a]: player_x -= speed
    if keys[pygame.K_d]: player_x += speed

    # --- Draw plane ---
    proj = [project(px, py, pz) for px, py, pz in plane_points]
    valid_proj = [p for p in proj if p]
    if len(valid_proj) >= 3:
        pygame.draw.polygon(screen, (50, 50, 50), valid_proj, 0)
    for a, b in plane_edges:
        if proj[a] and proj[b]:
            pygame.draw.line(screen, (80, 80, 80), proj[a], proj[b], 2)

    # --- Draw player ---
    pp = project(player_x, 0, player_z)
    if pp:
        pygame.draw.circle(screen, (0, 200, 255), pp, 6)

    # --- Spinning bullet: fully vectorized transform ---
    bullet_angle += 0.05
    cos_a = math.cos(bullet_angle)
    sin_a = math.sin(bullet_angle)

    x = vertices[:, 0]
    y = vertices[:, 1]
    z = vertices[:, 2]
    rx = x * cos_a - z * sin_a
    rz = x * sin_a + z * cos_a

    transformed = np.stack([rx, y, rz], axis=1) * scale_factor + bullet_pos

    screen_pts = project_batch(transformed)

    face_verts = screen_pts[all_faces]
    valid_mask = ~np.any(np.isnan(face_verts), axis=(1, 2))

    for face_pts in face_verts[valid_mask]:
        pygame.draw.polygon(screen, (255, 50, 50), face_pts.astype(int).tolist(), 0)

    pygame.display.flip()
    clock.tick(60)

pygame.quit()