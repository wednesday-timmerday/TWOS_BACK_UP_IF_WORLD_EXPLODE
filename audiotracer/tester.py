import pygame
import math
import sys

pygame.init()

W, H     = 1200, 740
SIDEBAR  = 320
SIM_W    = W - SIDEBAR

screen = pygame.display.set_mode((W, H))
pygame.display.set_caption("Audio Ray Tracer  //  prototype")
clock  = pygame.time.Clock()

# ── Prototype / engineering-sketchpad palette ─────────────────────────────────
BG          = (15,  17,  22)      # near-black background
GRID_COL    = (28,  32,  40)      # subtle grid
WALL_COL    = (200, 210, 220)     # bright walls
SOURCE_COL  = (255, 220,  60)     # amber source
PLAYER_COL  = ( 60, 200, 255)     # cyan player
RAY_DIRECT  = (255, 220,  60)     # amber direct path
RAY_BOUNCE  = ( 60, 200, 255)     # cyan bounced path
RAY_MISS    = ( 40,  44,  55)     # almost invisible misses
BOUNCE_DOT  = (180, 190, 210)
IMG_SRC_COL = ( 80,  80,  90)
UI_BG       = ( 18,  20,  26)
UI_BORDER   = ( 36,  40,  50)
TEXT_COL    = (220, 225, 235)
TEXT_DIM    = ( 90,  95, 110)
ACCENT      = ( 60, 200, 255)
GREEN       = ( 60, 210, 130)
ORANGE      = (255, 175,  60)
RED_COL     = (220,  80,  80)
LABEL_BG    = ( 26,  30,  38)

try:
    font_mono   = pygame.font.SysFont("JetBrains Mono", 13)
    font_mono_b = pygame.font.SysFont("JetBrains Mono", 13, bold=True)
    font_title  = pygame.font.SysFont("JetBrains Mono", 16, bold=True)
    font_big    = pygame.font.SysFont("JetBrains Mono", 20, bold=True)
except:
    font_mono   = pygame.font.SysFont("Courier New", 13)
    font_mono_b = pygame.font.SysFont("Courier New", 13, bold=True)
    font_title  = pygame.font.SysFont("Courier New", 16, bold=True)
    font_big    = pygame.font.SysFont("Courier New", 20, bold=True)

font_sm  = font_mono
font_med = font_mono_b

_overlay = pygame.Surface((W, H), pygame.SRCALPHA)

SOUND_SPEED_PX = 3430.0
R_REF          = 50.0
REFLECT_EPS    = 2.0   # nudge along wall normal after bounce (px) – fixes wall-penetration


# ══════════════════════════════════════════════════════════════════════════════
# Geometry primitives
# ══════════════════════════════════════════════════════════════════════════════

def ray_seg_intersect(ox, oy, dx, dy, x1, y1, x2, y2):
    """Ray vs line-segment. Returns (t, nx, ny) or None."""
    wx, wy = x2 - x1, y2 - y1
    denom  = dx * wy - dy * wx
    if abs(denom) < 1e-10:
        return None
    t = ((x1 - ox) * wy - (y1 - oy) * wx) / denom
    u = ((x1 - ox) * dy - (y1 - oy) * dx) / denom
    if t > 1e-4 and 0.0 <= u <= 1.0:
        length = math.hypot(wx, wy)
        nx, ny = -wy / length, wx / length
        if nx * dx + ny * dy > 0:
            nx, ny = -nx, -ny
        return t, nx, ny
    return None


def seg_seg_intersect(ax, ay, bx, by, cx, cy, dx2, dy2):
    def cross2(ux, uy, vx, vy): return ux*vy - uy*vx
    rx, ry = bx - ax, by - ay
    sx, sy = dx2 - cx, dy2 - cy
    denom  = cross2(rx, ry, sx, sy)
    if abs(denom) < 1e-10:
        return False
    t = cross2(cx - ax, cy - ay, sx, sy) / denom
    u = cross2(cx - ax, cy - ay, rx, ry) / denom
    return 1e-4 < t < 1 - 1e-4 and 1e-4 < u < 1 - 1e-4


def reflect_point(px, py, x1, y1, x2, y2):
    wx, wy = x2 - x1, y2 - y1
    ln2    = wx*wx + wy*wy
    if ln2 < 1e-12:
        return px, py
    t  = ((px - x1)*wx + (py - y1)*wy) / ln2
    fx = x1 + t*wx
    fy = y1 + t*wy
    return 2*fx - px, 2*fy - py


def circle_ray_intersect(ox, oy, dx, dy, cx, cy, r):
    fx, fy = ox - cx, oy - cy
    a = dx*dx + dy*dy
    b = 2*(fx*dx + fy*dy)
    c = fx*fx + fy*fy - r*r
    disc = b*b - 4*a*c
    if disc < 0:
        return None
    sq = math.sqrt(disc)
    for t in ((-b - sq) / (2*a), (-b + sq) / (2*a)):
        if t > 1e-4:
            return t
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Image Source Method
# ══════════════════════════════════════════════════════════════════════════════

def compute_image_sources(sx, sy, walls, max_order):
    results = [(sx, sy, [])]

    def recurse(ix, iy, seq):
        if len(seq) >= max_order:
            return
        for wi, wall in enumerate(walls):
            if seq and seq[-1] == wi:
                continue
            mx2, my2 = reflect_point(ix, iy, *wall.coords)
            new_seq = seq + [wi]
            results.append((mx2, my2, new_seq))
            recurse(mx2, my2, new_seq)

    recurse(sx, sy, [])
    return results


def validate_image_path(px, py, img_x, img_y, seq, walls, src_x, src_y, src_r):
    if not seq:
        dx = src_x - px
        dy = src_y - py
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            return None
        ndx, ndy = dx/dist, dy/dist
        t_src = circle_ray_intersect(px, py, ndx, ndy, src_x, src_y, src_r)
        if t_src is None:
            return None
        for wall in walls:
            h = ray_seg_intersect(px, py, ndx, ndy, *wall.coords)
            if h and h[0] < t_src - 1e-3:
                return None
        return [(px, py), (px + ndx * t_src, py + ndy * t_src)]

    partial = [(src_x, src_y)]
    for wi in reversed(seq):
        mx2, my2 = reflect_point(partial[-1][0], partial[-1][1], *walls[wi].coords)
        partial.append((mx2, my2))
    partial.reverse()

    path_pts = [(px, py)]
    cx, cy = px, py

    for step, wi in enumerate(seq):
        tx, ty = partial[step]
        dx = tx - cx
        dy = ty - cy
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            return None
        ndx, ndy = dx/dist, dy/dist

        h = ray_seg_intersect(cx, cy, ndx, ndy, *walls[wi].coords)
        if h is None:
            return None
        t_wall, _, _ = h

        bx, by = cx + ndx * t_wall, cy + ndy * t_wall

        blocked = False
        for oi, ow in enumerate(walls):
            if oi == wi:
                continue
            oh = ray_seg_intersect(cx, cy, ndx, ndy, *ow.coords)
            if oh and oh[0] < t_wall - 1e-3:
                blocked = True
                break
        if blocked:
            return None

        path_pts.append((bx, by))
        cx, cy = bx, by

    dx = src_x - cx
    dy = src_y - cy
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        return None
    ndx, ndy = dx/dist, dy/dist

    t_src = circle_ray_intersect(cx, cy, ndx, ndy, src_x, src_y, src_r)
    if t_src is None:
        return None

    for wall in walls:
        oh = ray_seg_intersect(cx, cy, ndx, ndy, *wall.coords)
        if oh and oh[0] < t_src - 1e-3:
            return None

    path_pts.append((cx + ndx * t_src, cy + ndy * t_src))
    return path_pts


def path_energy(path_pts, wall_abs_coeff, air_damp_db_per_100px):
    total_dist = 0.0
    for i in range(len(path_pts) - 1):
        ax, ay = path_pts[i]
        bx, by = path_pts[i+1]
        total_dist += math.hypot(bx - ax, by - ay)
    num_bounces = len(path_pts) - 2
    dB_per_px = air_damp_db_per_100px / 100.0
    air_energy = 10.0 ** (-dB_per_px * total_dist / 10.0)
    wall_energy = (1.0 - wall_abs_coeff) ** num_bounces
    r_eff = max(total_dist, R_REF)
    spread = (R_REF / r_eff) ** 2
    return air_energy * wall_energy * spread, total_dist, num_bounces


# ══════════════════════════════════════════════════════════════════════════════
# Random-ray tracer  (BUG FIX: nudge along normal, not ray direction)
# ══════════════════════════════════════════════════════════════════════════════

def trace_ray(ox, oy, dx, dy, walls, sx, sy, src_r,
              max_bounces, wall_abs_coeff, air_damp_db_per_100px):
    path   = [(ox, oy)]
    hits   = []
    energy = 1.0
    total_dist = 0.0
    dB_per_px  = air_damp_db_per_100px / 100.0
    air_factor = 10.0 ** (-dB_per_px / 10.0)

    for bounce in range(max_bounces + 1):
        t_src = circle_ray_intersect(ox, oy, dx, dy, sx, sy, src_r)

        closest = None
        for wall in walls:
            h = ray_seg_intersect(ox, oy, dx, dy, *wall.coords)
            if h and (closest is None or h[0] < closest[0]):
                closest = h

        t_wall = closest[0] if closest else float('inf')
        src_closer = (t_src is not None) and (t_src < t_wall - 1e-3)
        step = t_src if src_closer else (closest[0] if closest else 2000.0)

        energy     *= air_factor ** step
        total_dist += step

        if src_closer:
            r_eff    = max(total_dist, R_REF)
            energy  *= (R_REF / r_eff) ** 2
            path.append((ox + dx * t_src, oy + dy * t_src))
            return path, hits, True, max(0.0, energy), total_dist, bounce

        if closest is None:
            path.append((ox + dx * 2000, oy + dy * 2000))
            return path, hits, False, 0.0, total_dist, bounce

        t, nx, ny = closest
        hx, hy = ox + dx * t, oy + dy * t
        path.append((hx, hy))
        hits.append((hx, hy))

        energy *= (1.0 - wall_abs_coeff)
        if energy < 1e-5:
            return path, hits, False, 0.0, total_dist, bounce

        dot = dx*nx + dy*ny
        dx -= 2*dot*nx
        dy -= 2*dot*ny

        # FIX: nudge strictly along the outward normal, not along the (reflected)
        # ray direction.  A grazing reflection can leave the origin ambiguously
        # close to the wall surface; the normal nudge guarantees we're on the
        # correct side regardless of angle.
        ox = hx + nx * REFLECT_EPS
        oy = hy + ny * REFLECT_EPS

    return path, hits, False, 0.0, total_dist, max_bounces


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def lerp_color(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))

def energy_color(energy, bounces):
    t = min(energy * 6, 1.0)
    if bounces == 0:
        return lerp_color((180, 140, 20), (255, 220, 60), t)
    return lerp_color((20, 80, 140), (60, 200, 255), t)

def draw_crosshair(surf, x, y, r, color, width=1):
    pygame.draw.line(surf, color, (x-r, y), (x+r, y), width)
    pygame.draw.line(surf, color, (x, y-r), (x, y+r), width)

def draw_dashed_circle(surf, color, cx, cy, r, n=32, dash=True):
    pts = [(cx + r*math.cos(2*math.pi*i/n), cy + r*math.sin(2*math.pi*i/n)) for i in range(n)]
    for i in range(0, n, 2 if dash else 1):
        p1 = (int(pts[i][0]), int(pts[i][1]))
        p2 = (int(pts[(i+1)%n][0]), int(pts[(i+1)%n][1]))
        pygame.draw.line(surf, color, p1, p2, 1)


# ══════════════════════════════════════════════════════════════════════════════
# Wall
# ══════════════════════════════════════════════════════════════════════════════

class Wall:
    def __init__(self, x1, y1, x2, y2):
        self.coords = (x1, y1, x2, y2)

    def draw(self, surf):
        x1, y1, x2, y2 = self.coords
        pygame.draw.line(surf, WALL_COL, (int(x1), int(y1)), (int(x2), int(y2)), 2)
        # endpoint ticks
        for px, py in [(x1,y1),(x2,y2)]:
            pygame.draw.circle(surf, WALL_COL, (int(px), int(py)), 3)


def default_walls():
    m = 14
    return [
        Wall(m, m, SIM_W-m, m),
        Wall(SIM_W-m, m, SIM_W-m, H-m),
        Wall(SIM_W-m, H-m, m, H-m),
        Wall(m, H-m, m, m),
        Wall(200, 150, 200, 400),
        Wall(200, 400, 450, 400),
        Wall(450, 200, 450, 550),
        Wall(550, 100, 650, 300),
        Wall(620, 300, 750, 300),
        Wall(650, 400, 650, 600),
        Wall(300, 500, 550, 500),
        Wall(150, 500, 150, 620),
        Wall(750, 150, 750, 450),
        Wall(750, 150, 650, 150),
    ]


# ══════════════════════════════════════════════════════════════════════════════
# UI helpers
# ══════════════════════════════════════════════════════════════════════════════

def panel_header(surf, x, y, w, title):
    """Draw a section header with a full-width rule."""
    pygame.draw.line(surf, UI_BORDER, (x, y+1), (x+w, y+1), 1)
    lbl = font_sm.render(f"// {title}", True, TEXT_DIM)
    surf.blit(lbl, (x+6, y+5))
    return y + 22

def draw_slider(surf, x, y, w, val, mn, mx, label, fmt="{:.0f}"):
    surf.blit(font_sm.render(label, True, TEXT_DIM), (x, y))
    vstr = font_mono_b.render(fmt.format(val), True, ACCENT)
    surf.blit(vstr, (x + w - vstr.get_width(), y))
    by = y + 17
    # track
    pygame.draw.rect(surf, (35, 40, 52), (x, by, w, 4))
    frac = (val - mn) / (mx - mn) if mx != mn else 0
    fw   = int(frac * w)
    if fw > 0:
        pygame.draw.rect(surf, ACCENT, (x, by, fw, 4))
    # thumb
    tx = x + fw
    pygame.draw.rect(surf, UI_BG, (tx-4, by-4, 8, 12))
    pygame.draw.rect(surf, ACCENT, (tx-4, by-4, 8, 12), 1)
    return by + 2

def draw_bar_labeled(surf, x, y, w, h, frac, color, label_left, label_right):
    surf.blit(font_sm.render(label_left, True, TEXT_DIM), (x, y))
    rv = font_mono_b.render(label_right, True, color)
    surf.blit(rv, (x + w - rv.get_width(), y))
    by = y + 16
    pygame.draw.rect(surf, (35, 40, 52), (x, by, w, h))
    fw = int(frac * (w - 2))
    if fw > 0:
        pygame.draw.rect(surf, color, (x+1, by+1, fw, h-2))
    return by + h + 4


# ══════════════════════════════════════════════════════════════════════════════
# Simulation
# ══════════════════════════════════════════════════════════════════════════════

class Sim:
    def __init__(self):
        self.walls    = default_walls()
        self.source   = [400.0, 200.0]
        self.player   = [300.0, 450.0]
        self.player_r = 16
        self.source_r = 13

        self.num_rays       = 128
        self.max_bounces    = 5
        self.wall_abs       = 0.25
        self.air_damp       = 0.5
        self.source_pow_db  = 80.0
        self.img_order      = 2

        self.show_misses    = True
        self.show_dots      = True
        self.show_images    = True
        self.energy_mode    = True

        self.adding_wall  = False
        self.wall_start   = None
        self.preview_end  = None

        self.sliders = {
            "num_rays":      [128,   8,   360,  "rays  (MC estimate)",  "{:.0f}"],
            "max_bounces":   [5,     0,   10,   "max bounces",          "{:.0f}"],
            "img_order":     [2,     1,   3,    "image source order",   "{:.0f}"],
            "wall_abs":      [0.25,  0.0, 0.99, "wall absorption α",    "{:.2f}"],
            "air_damp":      [0.5,   0.0, 5.0,  "air damp dB/100px",    "{:.2f}"],
            "source_pow_db": [80.0, 40., 120.,  "source Lw  (dBSWL)",   "{:.0f}"],
        }
        self._slider_rects: dict = {}

        self.rays       = []
        self.img_paths   = []
        self.image_sources = []
        self.stats: dict = {}
        self.recalc()

    def recalc(self):
        px, py = self.player
        sx, sy = self.source

        rays = []
        for i in range(self.num_rays):
            angle = 2 * math.pi * i / self.num_rays
            dx, dy = math.cos(angle), math.sin(angle)
            rays.append(trace_ray(px, py, dx, dy, self.walls,
                                   sx, sy, self.source_r,
                                   self.max_bounces, self.wall_abs, self.air_damp))
        self.rays = rays

        images = compute_image_sources(sx, sy, self.walls, int(self.img_order))
        valid_paths = []
        for (ix, iy, seq) in images:
            pts = validate_image_path(px, py, ix, iy, seq, self.walls,
                                       sx, sy, self.source_r)
            if pts is not None:
                e, dist, nb = path_energy(pts, self.wall_abs, self.air_damp)
                if e > 1e-7:
                    valid_paths.append((pts, seq, e, dist, nb))
        self.img_paths = valid_paths
        self.image_sources = images

        self._compute_stats()

    def _compute_stats(self):
        hit     = [r for r in self.rays if r[2]]
        direct  = [r for r in hit if r[5] == 0]
        bounced = [r for r in hit if r[5] >  0]

        total_i  = sum(r[3] for r in hit)     / max(1, self.num_rays)
        direct_i = sum(r[3] for r in direct)  / max(1, self.num_rays)
        reverb_i = sum(r[3] for r in bounced) / max(1, self.num_rays)

        db = self.source_pow_db + 10.0*math.log10(total_i)  if total_i  > 0 else -120.0
        dr_db = 10.0*math.log10(direct_i / reverb_i) if (direct_i > 0 and reverb_i > 0) \
                else (60.0 if direct_i > 0 else -60.0)

        delays = [(r[4] / SOUND_SPEED_PX)*1000.0 for r in hit]
        earliest = min(delays) if delays else 0.0
        latest   = max(delays) if delays else 0.0

        has_direct = any(nb == 0 for _, _, _, _, nb in self.img_paths)

        # ── Direction: always use energy-weighted ray arrivals ─────────────
        # Ray-based: every ray that reached the source contributes its
        # *first-segment* direction (from listener toward first bounce/source).
        # This is always well-defined whenever any ray hits, so the arrow never
        # disappears due to image-source failures or diffuse-field cancellation.
        ax = ay = wsum = 0.0
        for ray_tuple in hit:
            path, _hits_list, _reached, energy, dist, nb = ray_tuple
            if len(path) < 2 or energy <= 0:
                continue
            vx = path[1][0] - path[0][0]
            vy = path[1][1] - path[0][1]
            ln = math.hypot(vx, vy)
            if ln < 1e-6:
                continue
            vx /= ln; vy /= ln
            ax += vx * energy
            ay += vy * energy
            wsum += energy

        conf = 0.0; dir_x = 0.0; dir_y = 0.0
        if wsum > 1e-12:
            ax /= wsum; ay /= wsum
            # conf = length of the mean unit vector ∈ [0,1].
            # 1 = all rays agree (clear direction); 0 = perfectly diffuse.
            conf = math.hypot(ax, ay)
            # Always produce a direction — even low-conf gets an arrow, just
            # drawn faint.  Avoid dividing by near-zero.
            mag = max(conf, 1e-6)
            dir_x, dir_y = ax / mag, ay / mag

        self.stats = {
            "total":       self.num_rays,
            "reached":     len(hit),
            "direct":      len(direct),
            "bounced":     len(bounced),
            "blocked":     self.num_rays - len(hit),
            "img_paths":   len(self.img_paths),
            "db":          db,
            "dr_db":       dr_db,
            "earliest_ms": earliest,
            "latest_ms":   latest,
            "conf":        conf,
            "dir_x":       dir_x,
            "dir_y":       dir_y,
            "has_direct":  has_direct,
        }

    def draw(self, surf):
        pygame.draw.rect(surf, BG, (0, 0, SIM_W, H))
        _overlay.fill((0, 0, 0, 0))

        # dot grid
        for gx in range(0, SIM_W, 40):
            for gy in range(0, H, 40):
                pygame.draw.circle(surf, GRID_COL, (gx, gy), 1)

        if self.show_misses:
            for path, _, reached, energy, dist, nb in self.rays:
                if not reached:
                    self._draw_path_ol(path, RAY_MISS, 1, 0.7)

        for path, hits_list, reached, energy, dist, nb in self.rays:
            if not reached:
                continue
            col   = energy_color(energy, nb) if self.energy_mode else (RAY_DIRECT if nb==0 else RAY_BOUNCE)
            self._draw_path_ol(path, col, 1, 0.18)

        for pts, seq, e, dist, nb in self.img_paths:
            col   = RAY_DIRECT if nb == 0 else RAY_BOUNCE
            self._draw_path_ol(pts, col, 2 if nb==0 else 1, 0.80)

        self._draw_dir_ol()
        surf.blit(_overlay, (0, 0))

        if self.show_dots:
            for pts, seq, e, dist, nb in self.img_paths:
                for bx, by in pts[1:-1]:
                    pygame.draw.circle(surf, BOUNCE_DOT, (int(bx), int(by)), 3)
                    pygame.draw.circle(surf, BG,         (int(bx), int(by)), 1)

        if self.show_images:
            for ix, iy, seq in self.image_sources:
                if not seq:
                    continue
                r = max(2, 5 - len(seq))
                pygame.draw.circle(surf, IMG_SRC_COL, (int(ix), int(iy)), r, 1)

        for w in self.walls:
            w.draw(surf)

        if self.adding_wall and self.wall_start and self.preview_end:
            pygame.draw.line(surf, (100, 120, 150), self.wall_start, self.preview_end, 1)
            pygame.draw.circle(surf, ACCENT, self.wall_start, 3)

        # ── Source S ────────────────────────────────────────────────────────
        sx, sy = int(self.source[0]), int(self.source[1])
        draw_dashed_circle(surf, SOURCE_COL, sx, sy, self.source_r + 8, n=24, dash=True)
        pygame.draw.circle(surf, SOURCE_COL, (sx, sy), self.source_r)
        pygame.draw.circle(surf, BG,         (sx, sy), self.source_r - 3)
        draw_crosshair(surf, sx, sy, self.source_r - 4, SOURCE_COL, 1)
        lbl = font_sm.render("S", True, SOURCE_COL)
        surf.blit(lbl, (sx - lbl.get_width()//2, sy - lbl.get_height()//2))

        # ── Player P ────────────────────────────────────────────────────────
        px, py = int(self.player[0]), int(self.player[1])
        draw_dashed_circle(surf, PLAYER_COL, px, py, self.player_r + 8, n=24, dash=True)
        pygame.draw.circle(surf, PLAYER_COL, (px, py), self.player_r)
        pygame.draw.circle(surf, BG,         (px, py), self.player_r - 3)
        draw_crosshair(surf, px, py, self.player_r - 4, PLAYER_COL, 1)
        lbl = font_sm.render("P", True, PLAYER_COL)
        surf.blit(lbl, (px - lbl.get_width()//2, py - lbl.get_height()//2))

    def _draw_path_ol(self, path, color, width, alpha):
        if len(path) < 2:
            return
        r, g, b = color[0], color[1], color[2]
        a = max(0, min(255, int(alpha * 255)))
        if a == 0:
            return
        for i in range(len(path)-1):
            pygame.draw.line(_overlay, (r, g, b, a),
                             (int(path[i][0]),   int(path[i][1])),
                             (int(path[i+1][0]), int(path[i+1][1])), width)

    def _draw_dir_ol(self):
        conf  = self.stats.get("conf",  0.0)
        dir_x = self.stats.get("dir_x", 0.0)
        dir_y = self.stats.get("dir_y", 0.0)
        # Only skip if no rays reached at all
        if self.stats.get("reached", 0) == 0:
            return
        px, py = self.player
        r  = self.player_r + 20
        ex = px + dir_x * r
        ey = py + dir_y * r
        col   = SOURCE_COL if self.stats.get("has_direct") else PLAYER_COL
        # conf controls opacity: diffuse fields show a faint arrow, direct fields bright
        a     = max(60, int(min(1.0, 0.4 + conf * 0.8) * 255))
        a_col = (*col, a)
        pygame.draw.line(_overlay, a_col, (int(px), int(py)), (int(ex), int(ey)), 2)
        perp  = (-dir_y * 5, dir_x * 5)
        tip   = (int(ex), int(ey))
        b1    = (int(ex - dir_x*9 + perp[0]), int(ey - dir_y*9 + perp[1]))
        b2    = (int(ex - dir_x*9 - perp[0]), int(ey - dir_y*9 - perp[1]))
        pygame.draw.polygon(_overlay, a_col, [tip, b1, b2])

    def draw_ui(self, surf):
        x0 = SIM_W
        pygame.draw.rect(surf, UI_BG, (x0, 0, SIDEBAR, H))
        pygame.draw.line(surf, UI_BORDER, (x0, 0), (x0, H), 1)

        x = x0 + 14
        y = 14

        # Title
        title = font_big.render("i luv math", True, TEXT_COL)
        surf.blit(title, (x, y)); y += 26
        sub = font_sm.render("AAAAAAAAAAAA", True, TEXT_DIM)
        surf.blit(sub, (x, y)); y += 22

        # ── Level ─────────────────────────────────────────────────────────
        y = panel_header(surf, x, y, SIDEBAR-28, "RECEIVED LEVEL")
        db   = self.stats.get("db",    -120)
        dr   = self.stats.get("dr_db",  0.0)
        conf = self.stats.get("conf",   0.0)
        db_min, db_max = 30.0, 90.0
        frac  = max(0.0, min(1.0, (db - db_min) / (db_max - db_min)))
        bar_col = GREEN if frac > 0.6 else (ORANGE if frac > 0.3 else RED_COL)
        db_str  = f"{db:.1f} dBSPL" if db > -100 else "—"
        y = draw_bar_labeled(surf, x+4, y+4, SIDEBAR-36, 7, frac, bar_col, "SPL", db_str)
        dr_col = GREEN if dr > 6 else (ORANGE if dr > 0 else RED_COL)
        dr_str = f"D/R  {dr:+.1f} dB" if self.stats.get("reached", 0) > 0 else "D/R  —"
        surf.blit(font_sm.render(dr_str, True, dr_col), (x+4, y)); y += 18
        surf.blit(font_sm.render(f"dir confidence  {int(conf*100):3d}%", True, TEXT_DIM), (x+4, y)); y += 22

        # ── Stats ─────────────────────────────────────────────────────────
        y = panel_header(surf, x, y, SIDEBAR-28, "STATISTICS")
        earliest = self.stats.get("earliest_ms", 0.0)
        latest   = self.stats.get("latest_ms",   0.0)
        rows = [
            ("rays cast",        str(self.stats.get("total",     0))),
            ("reached",          str(self.stats.get("reached",   0))),
            ("  ↳ direct",       str(self.stats.get("direct",    0))),
            ("  ↳ bounced",      str(self.stats.get("bounced",   0))),
            ("blocked",          str(self.stats.get("blocked",   0))),
            ("image src paths",  str(self.stats.get("img_paths", 0))),
            ("first arrival",    f"{earliest:.2f} ms"),
            ("last arrival",     f"{latest:.2f} ms"),
            ("reverb tail",      f"{latest-earliest:.2f} ms"),
        ]
        for label, val in rows:
            surf.blit(font_sm.render(label, True, TEXT_DIM), (x+4, y+3))
            tv = font_mono_b.render(val, True, TEXT_COL)
            surf.blit(tv, (x + SIDEBAR - 36 - tv.get_width(), y+3))
            y += 18
        y += 6

        # ── Parameters ────────────────────────────────────────────────────
        y = panel_header(surf, x, y, SIDEBAR-28, "PARAMETERS")
        self._slider_rects = {}
        for key, (val, mn, mx2, label, fmt) in self.sliders.items():
            ky = draw_slider(surf, x+4, y+6, SIDEBAR-36, val, mn, mx2, label, fmt)
            self._slider_rects[key] = (x+4, ky, SIDEBAR-36)
            y += 34
        y += 6

        # ── Controls ──────────────────────────────────────────────────────
        y = panel_header(surf, x, y, SIDEBAR-28, "KEYBINDS")
        binds = [
            ("[W]",    "add wall"),
            ("[Del]",  "remove last wall"),
            ("[M]",    "toggle miss rays"),
            ("[D]",    "toggle bounce dots"),
            ("[I]",    "toggle image ghosts"),
            ("[E]",    "energy colour mode"),
            ("[Esc]",  "cancel wall"),
        ]
        for key_lbl, desc in binds:
            kl = font_mono_b.render(key_lbl, True, ACCENT)
            surf.blit(kl, (x+4, y+3))
            surf.blit(font_sm.render(desc, True, TEXT_DIM), (x + 52, y+3))
            y += 18
        y += 6

        # ── Status bar ────────────────────────────────────────────────────
        mode = "ADD WALL" if self.adding_wall else "DRAG S / P"
        pygame.draw.line(surf, UI_BORDER, (x0, H-24), (W, H-24), 1)
        pygame.draw.rect(surf, UI_BG, (x0, H-24, SIDEBAR, 24))
        fps_lbl = font_sm.render(f"FPS {int(clock.get_fps()):3d}  //  {mode}", True, TEXT_DIM)
        surf.blit(fps_lbl, (x+4, H-18))

    def handle_slider(self, mx, my):
        for key, (sx, sy, sw) in self._slider_rects.items():
            if abs(my - sy) <= 8 and sx <= mx <= sx + sw:
                frac = max(0.0, min(1.0, (mx - sx) / sw))
                mn   = self.sliders[key][1]
                mx2  = self.sliders[key][2]
                raw  = mn + frac * (mx2 - mn)
                if key in ("num_rays", "max_bounces", "img_order"):
                    raw = int(round(raw))
                else:
                    raw = round(raw, 3)
                self.sliders[key][0] = raw
                setattr(self, key, raw)
                return True
        return False


# ══════════════════════════════════════════════════════════════════════════════
# Main loop
# ══════════════════════════════════════════════════════════════════════════════

def main():
    sim = Sim()
    active_slider = drag_src = drag_ply = False

    running = True
    while running:
        mx, my = pygame.mouse.get_pos()
        in_sim = mx < SIM_W

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                k = event.key
                if   k == pygame.K_ESCAPE:
                    sim.adding_wall = False; sim.wall_start = None
                elif k == pygame.K_w:
                    sim.adding_wall = not sim.adding_wall; sim.wall_start = None
                elif k in (pygame.K_DELETE, pygame.K_BACKSPACE):
                    if len(sim.walls) > 4:
                        sim.walls.pop(); sim.recalc()
                elif k == pygame.K_m:  sim.show_misses = not sim.show_misses
                elif k == pygame.K_d:  sim.show_dots   = not sim.show_dots
                elif k == pygame.K_i:  sim.show_images = not sim.show_images
                elif k == pygame.K_e:  sim.energy_mode = not sim.energy_mode

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if mx >= SIM_W:
                    if sim.handle_slider(mx, my):
                        active_slider = True; sim.recalc()
                elif sim.adding_wall:
                    if sim.wall_start is None:
                        sim.wall_start = (mx, my)
                    else:
                        sim.walls.append(Wall(sim.wall_start[0], sim.wall_start[1], mx, my))
                        sim.wall_start = None; sim.adding_wall = False; sim.recalc()
                else:
                    if math.hypot(mx-sim.source[0], my-sim.source[1]) < sim.source_r + 8:
                        drag_src = True
                    elif math.hypot(mx-sim.player[0], my-sim.player[1]) < sim.player_r + 8:
                        drag_ply = True

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                drag_src = drag_ply = active_slider = False

            elif event.type == pygame.MOUSEMOTION:
                if active_slider and mx >= SIM_W:
                    if sim.handle_slider(mx, my): sim.recalc()
                elif drag_src and in_sim:
                    sim.source = [float(mx), float(my)]; sim.recalc()
                elif drag_ply and in_sim:
                    sim.player = [float(mx), float(my)]; sim.recalc()
                elif sim.adding_wall and sim.wall_start:
                    sim.preview_end = (mx, my)

        screen.fill(BG)
        sim.draw(screen)
        sim.draw_ui(screen)
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()