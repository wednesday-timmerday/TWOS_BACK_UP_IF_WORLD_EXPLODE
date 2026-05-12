"""
DrawWorld editor â€” fixed edition

Fixes:
  - Enemy entries keep the actual sprite folder name
  - Toolbar drag-to-place is anchored in world space, not toolbar space
  - Single-click on toolbar still places objects
  - Inspector can edit enemy name inline
  - Selection/rename/drag/resize behavior preserved
  - Level switch prompt accepts letters/numbers/underscore/hyphen
  - Backspace works in the level switch prompt

  v2 fixes (toolbar drag overhaul):
  - drag_state now keeps toolbar_item separate from the created world object
    via a dedicated "toolbar_item" key, so kind/enemy_name are never lost
  - start_world is captured at MOUSEDOWN (converted to world coords) so the
    rubber-band origin is always the pixel where you pressed, not where you
    first moved enough to trigger DRAG_THRESH
  - _apply_new_drag is called every motion frame from that fixed origin, so
    the box grows naturally under the cursor
  - Single-click release (phase still "pending") creates a default-sized
    object centred on the click, matching the old behaviour
"""

import json
import pygame
import uuid
from pathlib import Path

from assetsLoader import Loader
from worlds.world_loader import World_loader
import sprites.Player.Player  # noqa: F401


pygame.init()

# â”€â”€ Display â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
BIG_SCREEN = pygame.display.set_mode((1280, 720))
pygame.display.set_caption("DrawWorld Editor")
WORLD_W, WORLD_H = 320, 180
SCREEN_SURF = pygame.Surface((WORLD_W, WORLD_H))
CLOCK = pygame.time.Clock()
SCALE = BIG_SCREEN.get_width() // WORLD_W

# â”€â”€ Fonts â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
FONT = pygame.font.SysFont("consolas", 16)
SMALL = pygame.font.SysFont("consolas", 12)
BIG_FONT = pygame.font.SysFont("consolas", 22)
BIG_SMALL = pygame.font.SysFont("consolas", 16)
TINY = pygame.font.SysFont("consolas", 13)

# â”€â”€ Layout â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
TOOLBAR_W = 210
INSPECTOR_W = 210
ICON_SIZE = 28
HANDLE_WLD = 4
PICK_TOL = 36
DRAG_THRESH = 5
DBLCLICK_MS = 280
CAM_SPEED = 700
SNAP_GRID = 8
SAVE_DEBOUNCE_MS = 600

SAVE_PATH = Path("worlds") / "level-spec.json"

# â”€â”€ Colours â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
C_PANEL = (18, 19, 22)
C_BORDER = (40, 42, 48)
C_TEXT = (190, 192, 200)
C_MUTED = (90, 95, 110)
C_ACCENT = (80, 130, 210)
C_TRIGGER = (200, 160, 48)
C_WALL = (48, 145, 200)
C_PLATFORM = (55, 175, 100)
C_SPAWN = (200, 80, 180)
C_ENEMY = (200, 80, 80)
C_SEL_OUT = (80, 130, 230)
C_HANDLE = (230, 185, 60)
C_INPUT_BG = (28, 30, 36)
C_INPUT_BORD = (55, 75, 120)

TOOL_KINDS = {
    "trigger": {"label": "Trigger", "hint": "drag to size", "color": C_TRIGGER},
    "wall": {"label": "Invisible wall", "hint": "drag to size", "color": C_WALL},
    "platform": {"label": "Platform", "hint": "drag to size", "color": C_PLATFORM},
    "spawn": {"label": "Spawn point", "hint": "click to place", "color": C_SPAWN},
    "enemy": {"label": "Enemy", "hint": "drag to place", "color": C_ENEMY},
}


def DPRINT(*a, **k):
    print("[DrawWorld]", *a, **k)


def snap(v, grid=SNAP_GRID):
    return round(v / grid) * grid


def apply_snap(x, y):
    if pygame.key.get_mods() & pygame.KMOD_SHIFT:
        return snap(x), snap(y)
    return int(x), int(y)


class ToolbarItem:
    def __init__(self, name, icon_surf, kind, enemy_name=None):
        self.name = name
        self.icon = icon_surf
        self.kind = kind
        self.enemy_name = enemy_name
        self.rect_big = pygame.Rect(0, 0, 0, 0)


def make_icon(color):
    s = pygame.Surface((ICON_SIZE, ICON_SIZE), pygame.SRCALPHA)
    pygame.draw.rect(s, (*color, 60), (0, 0, ICON_SIZE, ICON_SIZE), border_radius=4)
    pygame.draw.rect(s, (*color, 180), (0, 0, ICON_SIZE, ICON_SIZE), 1, border_radius=4)
    return s


class Editor:
    def __init__(self):
        player = sprites.Player.Player.Player(None)
        self.world = World_loader((WORLD_W, WORLD_H), player)
        self.current_level = self.world.current_level

        for key in ("enemies", "triggers", "invis_walls", "platforms", "save_points"):
            self.world.level_data.setdefault(key, [])

        self.toolbar_items = []
        self._build_toolbar()

        self.tool = "select"
        self.drag_state = {"phase": "idle"}
        self.resizing = None
        self.selected = None

        self.naming = False
        self.naming_text = ""
        self._naming_commit = None

        self.level_prompt_active = False
        self.level_prompt_text = ""

        self.last_click_time = 0
        self.last_click_obj = None

        self.pan_active = False
        self.pan_start_m = (0, 0)
        self.pan_start_cam = (0, 0)

        self.toolbar_visible = True
        self.toolbar_scroll = 0

        self._inspector_fields = []
        self._active_field = None
        self._rename_btn = pygame.Rect(0, 0, 0, 0)
        self._delete_btn = pygame.Rect(0, 0, 0, 0)

        self._dirty = False
        self._last_change = 0
        self.debug_pick = False
        self.dt = 0

        self._file_mtime = self._get_save_mtime()

    # â”€â”€ Toolbar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _build_toolbar(self):
        sprites_dir = Path("sprites")
        if sprites_dir.exists():
            for sub in sorted(sprites_dir.iterdir()):
                if not sub.is_dir():
                    continue
                icon = None
                frames = sub / "frames"
                if frames.exists():
                    for f in sorted(frames.iterdir()):
                        if f.suffix.lower() in (".png", ".jpg", ".jpeg"):
                            try:
                                surf = pygame.image.load(str(f)).convert_alpha()
                                icon = pygame.transform.smoothscale(surf, (ICON_SIZE, ICON_SIZE))
                                break
                            except Exception:
                                pass
                if icon is None:
                    icon = make_icon(C_ENEMY)
                self.toolbar_items.append(
                    ToolbarItem(sub.name, icon, "enemy", enemy_name=sub.name)
                )

        for kind, meta in TOOL_KINDS.items():
            if kind == "enemy":
                continue
            self.toolbar_items.append(ToolbarItem(meta["label"], make_icon(meta["color"]), kind))

        if not any(it.kind == "enemy" for it in self.toolbar_items):
            self.toolbar_items.append(ToolbarItem("Enemy", make_icon(C_ENEMY), "enemy", enemy_name="enemy"))

    # â”€â”€ Coordinate helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def toolbar_w(self):
        return TOOLBAR_W if self.toolbar_visible else 0

    def inspector_x(self):
        return BIG_SCREEN.get_width() - INSPECTOR_W

    def clamp_toolbar_scroll(self):
        item_h = ICON_SIZE + 20
        total = len(self.toolbar_items) * item_h + 60
        max_s = max(0, total - (BIG_SCREEN.get_height() - 40))
        self.toolbar_scroll = max(0, min(self.toolbar_scroll, max_s))

    def screen_to_world(self, sx, sy):
        return (sx - self.toolbar_w()) // SCALE + self.world.cam_x, sy // SCALE + self.world.cam_y

    def world_to_screen(self, wx, wy):
        return wx - self.world.cam_x, wy - self.world.cam_y

    def world_to_big(self, wx, wy):
        sx, sy = self.world_to_screen(wx, wy)
        return sx * SCALE + self.toolbar_w(), sy * SCALE

    # â”€â”€ Persistence â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def mark_dirty(self):
        self._dirty = True
        self._last_change = pygame.time.get_ticks()

    def flush_save_if_needed(self):
        if self._dirty and pygame.time.get_ticks() - self._last_change >= SAVE_DEBOUNCE_MS:
            self._do_save()

    def _do_save(self):
        try:
            with open(SAVE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.world.world_data, f, indent=2)
            self._dirty = False
            self._file_mtime = self._get_save_mtime()
            DPRINT("Saved â†’", SAVE_PATH)
        except Exception as e:
            DPRINT("Save failed:", e)

    def save_world(self):
        self._do_save()

    # â”€â”€ Geometry helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _obj_rect(self, obj):
        if isinstance(obj, dict):
            t = obj.get("type")
            if t == "trigger":
                return obj["x"], obj["y"], obj["w"], obj["h"]
            if t == "platform":
                return obj["x"], obj["y"], obj["width"], obj["height"]
            if t == "spawn":
                return obj["pos_x"] - 8, obj["pos_y"] - 8, 16, 16
            if "position" in obj:
                p = obj["position"]
                return p[0] - 8, p[1] - 8, 16, 16
        elif isinstance(obj, list) and len(obj) >= 4:
            return obj[0], obj[1], obj[2], obj[3]
        return None

    def corners_of(self, obj):
        r = self._obj_rect(obj)
        if r is None:
            return []
        x, y, w, h = r
        return [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]

    def get_corner_hit(self, obj, wx, wy):
        tol = HANDLE_WLD + 2
        for i, (cx, cy) in enumerate(self.corners_of(obj)):
            if abs(wx - cx) <= tol and abs(wy - cy) <= tol:
                return i
        return None

    def pick_at(self, wx, wy):
        tol = PICK_TOL
        ld = self.world.level_data

        for e in reversed(ld.get("enemies", [])):
            pos = e.get("position")
            if pos and abs(wx - pos[0]) <= tol and abs(wy - pos[1]) <= tol:
                return e

        for t in reversed(ld.get("triggers", [])):
            if (t["x"] - tol) <= wx <= (t["x"] + t["w"] + tol) and (t["y"] - tol) <= wy <= (t["y"] + t["h"] + tol):
                return t

        for p in reversed(ld.get("platforms", [])):
            if (p["x"] - tol) <= wx <= (p["x"] + p["width"] + tol) and (p["y"] - tol) <= wy <= (p["y"] + p["height"] + tol):
                return p

        for s in reversed(ld.get("save_points", [])):
            if abs(wx - s.get("pos_x", 0)) <= tol and abs(wy - s.get("pos_y", 0)) <= tol:
                return s

        for w in reversed(ld.get("invis_walls", [])):
            if (w[0] - tol) <= wx <= (w[0] + w[2] + tol) and (w[1] - tol) <= wy <= (w[1] + w[3] + tol):
                return w

        return None

    # â”€â”€ Create helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _new_obj(self, kind, wx, wy, enemy_name=None):
        ld = self.world.level_data
        uid = str(uuid.uuid4())

        if kind == "enemy":
            obj = {
                "type": enemy_name or "enemy",
                "position": [int(wx), int(wy)],
                "id": uid,
            }
            ld.setdefault("enemies", []).append(obj)
            return obj

        if kind == "trigger":
            obj = {"type": "trigger", "x": int(wx), "y": int(wy), "w": 96, "h": 56, "name": "", "id": uid}
            ld.setdefault("triggers", []).append(obj)
            return obj

        if kind == "wall":
            obj = [int(wx), int(wy), 96, 56, ""]
            ld.setdefault("invis_walls", []).append(obj)
            return obj

        if kind == "platform":
            obj = {"type": "platform", "x": int(wx), "y": int(wy), "width": 128, "height": 20, "id": uid}
            ld.setdefault("platforms", []).append(obj)
            return obj

        if kind == "spawn":
            obj = {"type": "spawn", "came_from": 0, "pos_x": int(wx), "pos_y": int(wy), "id": uid}
            ld.setdefault("save_points", []).append(obj)
            return obj

        return None

    def _drag_offset(self, obj, wx, wy):
        if isinstance(obj, dict):
            t = obj.get("type")
            if "position" in obj:
                p = obj["position"]
                return wx - p[0], wy - p[1]
            if t in ("trigger", "platform"):
                return wx - obj["x"], wy - obj["y"]
            if t == "spawn":
                return wx - obj["pos_x"], wy - obj["pos_y"]
        elif isinstance(obj, list):
            return wx - obj[0], wy - obj[1]
        return 0, 0

    def _apply_drag(self, obj, wx, wy, offx, offy):
        nx, ny = apply_snap(wx - offx, wy - offy)
        if isinstance(obj, dict):
            t = obj.get("type")
            if "position" in obj:
                obj["position"] = [nx, ny]
                self._sync_enemy(obj)
            elif t in ("trigger", "platform"):
                obj["x"], obj["y"] = nx, ny
            elif t == "spawn":
                obj["pos_x"], obj["pos_y"] = nx, ny
        elif isinstance(obj, list):
            obj[0], obj[1] = nx, ny

    def _apply_new_drag(self, obj, start_wx, start_wy, wx, wy):
        if isinstance(obj, dict):
            t = obj.get("type")
            if t == "trigger":
                obj["x"], obj["y"] = apply_snap(min(start_wx, wx), min(start_wy, wy))
                obj["w"] = max(8, int(abs(wx - start_wx)))
                obj["h"] = max(8, int(abs(wy - start_wy)))
            elif t == "platform":
                obj["x"], obj["y"] = apply_snap(min(start_wx, wx), min(start_wy, wy))
                obj["width"] = max(8, int(abs(wx - start_wx)))
                obj["height"] = max(8, int(abs(wy - start_wy)))
            elif t == "spawn":
                obj["pos_x"], obj["pos_y"] = apply_snap(wx, wy)
            elif "position" in obj:
                obj["position"] = list(apply_snap(wx, wy))
        elif isinstance(obj, list):
            obj[0], obj[1] = apply_snap(min(start_wx, wx), min(start_wy, wy))
            obj[2] = max(8, int(abs(wx - start_wx)))
            obj[3] = max(8, int(abs(wy - start_wy)))

    # â”€â”€ Enemy sync â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _sync_enemy(self, edict):
        try:
            pos = edict.get("position")
            if not pos:
                return
            nx, ny = int(pos[0]), int(pos[1])
            tid = edict.get("id")
            insts = getattr(self.world, "enemies", [])

            for inst in insts:
                if getattr(inst, "id", None) == tid:
                    inst.world_x = nx
                    inst.world_y = ny
                    if hasattr(inst, "pos"):
                        inst.pos = [nx, ny]
                    return

            best_inst = None
            best_d = 999999
            for inst in insts:
                ix = getattr(inst, "world_x", None)
                iy = getattr(inst, "world_y", None)
                if ix is None:
                    p = getattr(inst, "pos", None)
                    if p:
                        ix, iy = p[0], p[1]
                if ix is None:
                    continue
                d = abs(ix - nx) + abs(iy - ny)
                if d < best_d:
                    best_d = d
                    best_inst = inst

            if best_inst and best_d < PICK_TOL * 3:
                best_inst.world_x = nx
                best_inst.world_y = ny
                if hasattr(best_inst, "pos"):
                    best_inst.pos = [nx, ny]
        except Exception:
            pass

    def _annotate_ids(self):
        try:
            eds = self.world.level_data.get("enemies", [])
            insts = getattr(self.world, "enemies", [])
            pos_to_id = {}
            for e in eds:
                if isinstance(e, dict) and e.get("id") and e.get("position"):
                    pos_to_id[(round(e["position"][0]), round(e["position"][1]))] = e["id"]

            for inst in insts:
                ix = getattr(inst, "world_x", None)
                iy = getattr(inst, "world_y", None)
                if ix is None:
                    p = getattr(inst, "pos", None)
                    if p:
                        ix, iy = p[0], p[1]
                if ix is None:
                    continue
                best_id = pos_to_id.get((round(ix), round(iy)))
                if best_id is None:
                    best_d = 999
                    for (px, py), eid in pos_to_id.items():
                        d = abs(ix - px) + abs(iy - py)
                        if d < best_d:
                            best_d = d
                            best_id = eid
                if best_id:
                    inst.id = best_id
        except Exception:
            pass

    # â”€â”€ Level switching â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def switch_level(self, level_id):
        self.save_world()
        key = f"level_{level_id}"
        self.world.world_data.setdefault(key, {
            "enemies": [], "triggers": [], "invis_walls": [], "platforms": [], "save_points": []
        })
        self.current_level = self.world.current_level = level_id
        self.world.level_data = self.world.world_data[key]
        for k in ("enemies", "triggers", "invis_walls", "platforms", "save_points"):
            self.world.level_data.setdefault(k, [])
        self.world.load_layers()
        self.world.build_collision_mask_new()
        self.world.load_enemies()
        self.world.cam_x = self.world.cam_y = 0
        self.selected = self.resizing = None
        self.drag_state = {"phase": "idle"}
        self._annotate_ids()

    # â”€â”€ Mouse â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def handle_mouse_down(self, ev):
        mx, my = ev.pos
        tw = self.toolbar_w()
        iw = self.inspector_x()

        if ev.button == 2:
            self.pan_active = True
            self.pan_start_m = (mx, my)
            self.pan_start_cam = (self.world.cam_x, self.world.cam_y)
            return

        if ev.button != 1:
            return

        if self.naming:
            return

        if mx >= iw:
            return

        if tw and mx < tw:
            # â”€â”€ Toolbar click/drag start â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            y0 = 30 - self.toolbar_scroll
            for it in self.toolbar_items:
                r = pygame.Rect(8, y0, tw - 16, ICON_SIZE + 4)
                if r.collidepoint(mx, my):
                    # Convert the click position to world coords so we have a
                    # fixed drag origin even before the cursor enters the canvas.
                    # screen_to_world clamps correctly once mx >= tw, but during
                    # the toolbar phase we store the raw mouse pos and convert
                    # on first entry to the world area (see handle_mouse_motion).
                    self.drag_state = {
                        "phase": "pending",
                        "mode": "toolbar_new",
                        # Keep the toolbar item separate so kind/enemy_name are
                        # never overwritten when we create the world object.
                        "toolbar_item": it,
                        # Screen-space origin for DRAG_THRESH testing.
                        "start_mouse": (mx, my),
                        # World object created lazily on first motion into canvas.
                        "world_obj": None,
                    }
                    self.tool = it.name
                    return
                y0 += ICON_SIZE + 20
            return

        # â”€â”€ World area click â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        wx, wy = self.screen_to_world(mx, my)
        hit = self.pick_at(wx, wy)
        now = pygame.time.get_ticks()

        if hit:
            self.selected = hit
            if self.last_click_obj is hit and (now - self.last_click_time) <= DBLCLICK_MS:
                self._open_rename(hit)
            self.last_click_obj = hit
            self.last_click_time = now

            corner = self.get_corner_hit(hit, wx, wy)
            if corner is not None:
                self.resizing = {"obj": hit, "corner": corner}
            else:
                off = self._drag_offset(hit, wx, wy)
                self.drag_state = {
                    "phase": "pending",
                    "mode": "existing",
                    "obj": hit,
                    "start_mouse": (mx, my),
                    "offset": off,
                }
        else:
            self.selected = None

    def handle_mouse_up(self, ev):
        if ev.button == 2:
            self.pan_active = False
            return
        if ev.button != 1:
            return

        mx, my = ev.pos
        wx, wy = self.screen_to_world(mx, my)
        ds = self.drag_state

        if ds["phase"] == "pending" and ds.get("mode") == "toolbar_new":
            # â”€â”€ Single click (no drag): place a default-sized object â”€â”€
            # Only act if the cursor ended up in the world area.
            if mx >= self.toolbar_w():
                it = ds["toolbar_item"]
                new_obj = self._new_obj(it.kind, wx, wy, it.enemy_name)
                if new_obj is not None:
                    self.selected = new_obj
                    self._load_enemies_safe()
                    self.mark_dirty()

        elif ds["phase"] in ("pending", "active"):
            # Finalise an in-progress drag on an existing object.
            if ds.get("mode") == "new":
                self._load_enemies_safe()
            self.mark_dirty()

        if self.resizing:
            self.mark_dirty()

        self.drag_state = {"phase": "idle"}
        self.resizing = None

    def handle_mouse_motion(self, ev):
        mx, my = ev.pos
        wx, wy = self.screen_to_world(mx, my)

        if self.pan_active:
            pmx, pmy = self.pan_start_m
            self.world.cam_x = int(self.pan_start_cam[0] - (mx - pmx) // SCALE)
            self.world.cam_y = int(self.pan_start_cam[1] - (my - pmy) // SCALE)
            return

        ds = self.drag_state

        # â”€â”€ Toolbar-new pending: wait for DRAG_THRESH then enter world â”€â”€
        if ds["phase"] == "pending" and ds.get("mode") == "toolbar_new":
            smx, smy = ds["start_mouse"]
            moved = abs(mx - smx) > DRAG_THRESH or abs(my - smy) > DRAG_THRESH
            if not moved:
                return

            # Don't create anything until the cursor has left the toolbar.
            if self.toolbar_visible and mx < self.toolbar_w():
                return

            it = ds["toolbar_item"]
            # wx/wy is already in world space at the current cursor position.
            # This becomes both the object's initial position AND the rubber-band
            # origin, so the box grows away from where you first entered the canvas.
            new_obj = self._new_obj(it.kind, wx, wy, it.enemy_name)
            if new_obj is None:
                self.drag_state = {"phase": "idle"}
                return

            self.selected = new_obj
            # Transition to the active drag state with a clean structure.
            self.drag_state = {
                "phase": "active",
                "mode": "new",
                "toolbar_item": it,       # kept for reference
                "world_obj": new_obj,
                "obj": new_obj,           # alias used by existing code paths
                "kind": it.kind,
                # Anchor in world space: the point where dragging started.
                "start_world": (wx, wy),
            }
            return

        # â”€â”€ Active drag â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if ds["phase"] == "active":
            obj = ds["obj"]
            if ds["mode"] == "existing":
                offx, offy = ds.get("offset", (0, 0))
                self._apply_drag(obj, wx, wy, offx, offy)
            else:
                # New object being sized by dragging.
                kind = ds.get("kind", "")
                is_point = kind in ("enemy", "spawn") or (
                    isinstance(obj, dict) and "position" in obj) or (
                    isinstance(obj, dict) and obj.get("type") == "spawn")

                if is_point:
                    # Point objects just follow the cursor.
                    self._apply_drag(obj, wx, wy, 0, 0)
                else:
                    swx, swy = ds["start_world"]
                    self._apply_new_drag(obj, swx, swy, wx, wy)
            self.mark_dirty()

        # â”€â”€ Pending existing-object drag â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if ds["phase"] == "pending" and ds.get("mode") == "existing":
            smx, smy = ds["start_mouse"]
            moved = abs(mx - smx) > DRAG_THRESH or abs(my - smy) > DRAG_THRESH
            if moved:
                ds["phase"] = "active"

        # â”€â”€ Resize â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if self.resizing:
            obj = self.resizing["obj"]
            corner = self.resizing["corner"]
            self._apply_resize(obj, corner, wx, wy)
            self.mark_dirty()

    def _apply_resize(self, obj, corner, wx, wy):
        wx, wy = int(wx), int(wy)
        if isinstance(obj, dict) and obj.get("type") == "trigger":
            self._resize_rect_dict(obj, corner, wx, wy, "x", "y", "w", "h")
        elif isinstance(obj, dict) and obj.get("type") == "platform":
            self._resize_rect_dict(obj, corner, wx, wy, "x", "y", "width", "height")
        elif isinstance(obj, list) and len(obj) >= 4:
            tmp = {"x": obj[0], "y": obj[1], "w": obj[2], "h": obj[3]}
            self._resize_rect_dict(tmp, corner, wx, wy, "x", "y", "w", "h")
            obj[0], obj[1], obj[2], obj[3] = tmp["x"], tmp["y"], tmp["w"], tmp["h"]

    def _resize_rect_dict(self, obj, corner, wx, wy, xk, yk, wk, hk):
        x, y, w, h = obj[xk], obj[yk], obj[wk], obj[hk]
        brx, bry = x + w, y + h
        if corner == 0:
            obj[xk] = wx; obj[yk] = wy
            obj[wk] = max(8, brx - wx); obj[hk] = max(8, bry - wy)
        elif corner == 1:
            obj[yk] = wy
            obj[wk] = max(8, wx - x); obj[hk] = max(8, bry - wy)
        elif corner == 2:
            obj[xk] = wx
            obj[wk] = max(8, brx - wx); obj[hk] = max(8, wy - y)
        elif corner == 3:
            obj[wk] = max(8, wx - x); obj[hk] = max(8, wy - y)

    def handle_mouse_wheel(self, ev):
        mx, my = pygame.mouse.get_pos()
        if mx < self.toolbar_w():
            delta = getattr(ev, "y", 0)
            self.toolbar_scroll -= int(delta * (ICON_SIZE // 2))
            self.clamp_toolbar_scroll()

    # â”€â”€ Inspector interaction â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _inspector_click(self, mx, my):
        for rect, getter, setter, fid in self._inspector_fields:
            if rect.collidepoint(mx, my):
                self._active_field = {"rect": rect, "getter": getter, "setter": setter, "id": fid, "text": str(getter())}
                return True
        self._active_field = None
        return False

    def _inspector_key(self, ev):
        af = self._active_field
        if af is None:
            return False
        if ev.key == pygame.K_RETURN:
            af["setter"](af["text"])
            self.mark_dirty()
            self._active_field = None
        elif ev.key == pygame.K_ESCAPE:
            self._active_field = None
        elif ev.key == pygame.K_BACKSPACE:
            af["text"] = af["text"][:-1]
        elif ev.unicode:
            af["text"] += ev.unicode
        return True

    # â”€â”€ Rename popup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _open_rename(self, obj):
        self.naming = True
        if isinstance(obj, dict):
            t = obj.get("type")
            if t == "trigger":
                self.naming_text = obj.get("name", "")
                def commit(txt): obj["name"] = txt
            elif t == "spawn":
                self.naming_text = str(obj.get("came_from", 0))
                def commit(txt):
                    try:
                        obj["came_from"] = int(txt)
                    except ValueError:
                        pass
            elif t == "enemy":
                self.naming_text = obj.get("type", "enemy")
                def commit(txt): obj["type"] = txt or "enemy"
            elif "position" in obj:
                self.naming_text = obj.get("name", "")
                def commit(txt): obj["name"] = txt
            else:
                self.naming_text = ""
                def commit(txt): pass
        elif isinstance(obj, list):
            self.naming_text = obj[4] if len(obj) >= 5 else ""
            def commit(txt):
                while len(obj) < 5:
                    obj.append("")
                obj[4] = txt
        else:
            self.naming_text = ""
            def commit(txt): pass
        self._naming_commit = commit

    def _commit_naming(self):
        if self._naming_commit:
            self._naming_commit(self.naming_text.strip())
        self.naming = False
        self.naming_text = ""
        self._naming_commit = None
        self.mark_dirty()

    def _cancel_naming(self):
        self.naming = False
        self.naming_text = ""
        self._naming_commit = None

    def _get_save_mtime(self):
        try:
            return SAVE_PATH.stat().st_mtime
        except Exception:
            return 0

    def _check_auto_reload(self):
        if self._dirty:
            return
        try:
            mt = self._get_save_mtime()
            if mt != self._file_mtime:
                self._file_mtime = mt
                with open(SAVE_PATH, "r", encoding="utf-8") as f:
                    new_data = json.load(f)
                self.world.world_data = new_data
                key = f"level_{self.current_level}"
                if key in new_data:
                    self.world.level_data = new_data[key]
                    for k in ("enemies", "triggers", "invis_walls", "platforms", "save_points"):
                        self.world.level_data.setdefault(k, [])
                self.selected = None
                self._load_enemies_safe()
                DPRINT("Auto-reloaded from", SAVE_PATH)
        except Exception as e:
            DPRINT("Auto-reload error:", e)

    # â”€â”€ Update / render â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def update(self, dt):
        self.dt = dt
        keys = pygame.key.get_pressed()
        speed = CAM_SPEED * (dt / 1000.0)
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.world.cam_x -= int(speed)
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.world.cam_x += int(speed)
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            self.world.cam_y -= int(speed)
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            self.world.cam_y += int(speed)
        self.clamp_toolbar_scroll()
        self.flush_save_if_needed()
        self._check_auto_reload()

    def _draw_handles_world(self, surf, obj):
        for cx, cy in self.corners_of(obj):
            sx, sy = self.world_to_screen(cx, cy)
            hw = HANDLE_WLD
            pygame.draw.rect(surf, C_HANDLE, (int(sx - hw), int(sy - hw), hw * 2, hw * 2))

    def draw_level_objects(self, surf):
        ld = self.world.level_data

        for w in ld.get("invis_walls", []):
            sx, sy = self.world_to_screen(w[0], w[1])
            r = pygame.Rect(sx, sy, w[2], w[3])
            s = pygame.Surface((w[2], w[3]), pygame.SRCALPHA)
            s.fill((*C_WALL, 20))
            surf.blit(s, (sx, sy))
            pygame.draw.rect(surf, C_WALL, r, 1)

        for p in ld.get("platforms", []):
            sx, sy = self.world_to_screen(p["x"], p["y"])
            r = pygame.Rect(sx, sy, p["width"], p["height"])
            s = pygame.Surface((p["width"], p["height"]), pygame.SRCALPHA)
            s.fill((*C_PLATFORM, 160))
            surf.blit(s, (sx, sy))
            pygame.draw.rect(surf, (20, 90, 50), r, 1)

        for t in ld.get("triggers", []):
            sx, sy = self.world_to_screen(t["x"], t["y"])
            r = pygame.Rect(sx, sy, t["w"], t["h"])
            s = pygame.Surface((t["w"], t["h"]), pygame.SRCALPHA)
            s.fill((*C_TRIGGER, 25))
            surf.blit(s, (sx, sy))
            pygame.draw.rect(surf, C_TRIGGER, r, 1)
            nm = t.get("name", "")
            if nm:
                surf.blit(SMALL.render(nm[:12], True, C_TRIGGER), (sx + 1, sy + 1))

        for sp in ld.get("save_points", []):
            sx, sy = self.world_to_screen(sp.get("pos_x", 0), sp.get("pos_y", 0))
            pygame.draw.circle(surf, C_SPAWN, (int(sx), int(sy)), 5)
            pygame.draw.circle(surf, C_SPAWN, (int(sx), int(sy)), 8, 1)
            surf.blit(SMALL.render(f"{sp.get('came_from', 0)}", True, C_SPAWN), (int(sx) + 10, int(sy) - 5))

        for e in ld.get("enemies", []):
            pos = e.get("position")
            if not pos:
                continue
            sx, sy = self.world_to_screen(pos[0], pos[1])
            pygame.draw.circle(surf, C_ENEMY, (int(sx), int(sy)), 6)

        if self.selected:
            self._draw_handles_world(surf, self.selected)

    def render_world(self, surf):
        surf.fill((28, 30, 36))
        px = self.world.cam_x + WORLD_W // 2
        py = self.world.cam_y + WORLD_H // 2

        if not hasattr(self.world, "collision_background") or self.world.collision_background is None:
            try:
                self.world._render_collision_background()
            except Exception:
                pass

        orig_cam = self.world.update_camera

        def _freeze(a, b):
            self.world.cam_x = max(0, min(self.world.cam_x, getattr(self.world, "max_cam_x", self.world.cam_x)))
            self.world.cam_y = max(0, min(self.world.cam_y, getattr(self.world, "max_cam_y", self.world.cam_y)))

        self.world.update_camera = _freeze
        try:
            self.world.draw_world(surf, px, py)
        except Exception as e:
            DPRINT("draw_world error:", e)
        finally:
            self.world.update_camera = orig_cam

        self.draw_level_objects(surf)

    def draw_toolbar(self, surf):
        if not self.toolbar_visible:
            return
        tw = self.toolbar_w()
        H = surf.get_height()
        pygame.draw.rect(surf, C_PANEL, (0, 0, tw, H))
        pygame.draw.line(surf, C_BORDER, (tw, 0), (tw, H))

        sections = [
            ("GEOMETRY", [it for it in self.toolbar_items if it.kind in ("trigger", "wall", "platform")]),
            ("ENTITIES", [it for it in self.toolbar_items if it.kind in ("enemy", "spawn")]),
        ]
        y = 12 - self.toolbar_scroll
        for sec_label, items in sections:
            if y > H:
                break
            if y > -20:
                surf.blit(TINY.render(sec_label, True, C_MUTED), (12, y + 2))
            y += 22
            for it in items:
                row_h = ICON_SIZE + 12
                r = pygame.Rect(8, y, tw - 16, row_h)
                it.rect_big = r
                if y + row_h > 0 and y < H:
                    is_sel = self.tool == it.name
                    bg = (28, 32, 44) if is_sel else C_PANEL
                    border_c = C_ACCENT if is_sel else C_BORDER
                    pygame.draw.rect(surf, bg, r, border_radius=5)
                    pygame.draw.rect(surf, border_c, r, 1, border_radius=5)
                    surf.blit(it.icon, (r.x + 6, r.y + (row_h - ICON_SIZE) // 2))
                    kind_meta = TOOL_KINDS.get(it.kind, {})
                    color = kind_meta.get("color", C_TEXT)
                    name_s = BIG_SMALL.render(it.name, True, color)
                    hint_s = TINY.render(kind_meta.get("hint", ""), True, C_MUTED)
                    tx = r.x + ICON_SIZE + 14
                    surf.blit(name_s, (tx, r.y + 4))
                    surf.blit(hint_s, (tx, r.y + 4 + name_s.get_height() + 1))
                y += row_h + 8
            y += 6

        badge_y = H - 36
        pygame.draw.line(surf, C_BORDER, (0, badge_y - 4), (tw, badge_y - 4))
        surf.blit(TINY.render(f"Tool: {self.tool}", True, C_ACCENT), (12, badge_y + 2))

    def draw_inspector(self, surf):
        ix = self.inspector_x()
        H = surf.get_height()
        pygame.draw.rect(surf, C_PANEL, (ix, 0, INSPECTOR_W, H))
        pygame.draw.line(surf, C_BORDER, (ix, 0), (ix, H))

        surf.blit(BIG_SMALL.render("PROPERTIES", True, C_MUTED), (ix + 12, 14))
        pygame.draw.line(surf, C_BORDER, (ix, 38), (ix + INSPECTOR_W, 38))

        self._inspector_fields = []

        if self.selected is None:
            surf.blit(TINY.render("Nothing selected.", True, C_MUTED), (ix + 12, 52))
            return

        obj = self.selected
        if isinstance(obj, dict):
            t = obj.get("type", "unknown")
            col = {"trigger": C_TRIGGER, "platform": C_PLATFORM, "spawn": C_SPAWN, "enemy": C_ENEMY}.get(t, C_TEXT)
            badge = BIG_SMALL.render(t, True, col)
            surf.blit(badge, (ix + 12, 46))
            line_y = 46 + badge.get_height() + 8
            pygame.draw.line(surf, C_BORDER, (ix + 8, line_y), (ix + INSPECTOR_W - 8, line_y))
            fy = line_y + 10

            fy = self._insp_field(surf, ix, fy, "x", lambda: str(self._get_obj_x(obj)), lambda v: self._set_obj_x(obj, v))
            fy = self._insp_field(surf, ix, fy, "y", lambda: str(self._get_obj_y(obj)), lambda v: self._set_obj_y(obj, v))
            if t not in ("spawn",) and "position" not in obj:
                fy = self._insp_field(surf, ix, fy, "w", lambda: str(self._get_obj_w(obj)), lambda v: self._set_obj_w(obj, v))
                fy = self._insp_field(surf, ix, fy, "h", lambda: str(self._get_obj_h(obj)), lambda v: self._set_obj_h(obj, v))
            if t == "trigger":
                fy = self._insp_field(surf, ix, fy, "name", lambda: obj.get("name", ""), lambda v: obj.update({"name": v}))
            elif t == "spawn":
                fy = self._insp_field(surf, ix, fy, "came_from", lambda: str(obj.get("came_from", 0)),
                                      lambda v: obj.update({"came_from": int(v) if v.isdigit() else 0}))
            elif t == "enemy":
                fy = self._insp_field(surf, ix, fy, "type",
                    lambda: obj.get("type", "enemy"),
                    lambda v: obj.update({"type": v or "enemy"}))

        elif isinstance(obj, list):
            badge = BIG_SMALL.render("wall", True, C_WALL)
            surf.blit(badge, (ix + 12, 46))
            fy = 46 + badge.get_height() + 18
            fy = self._insp_field(surf, ix, fy, "x", lambda: str(obj[0]), lambda v: obj.__setitem__(0, int(v) if v.lstrip("-").isdigit() else obj[0]))
            fy = self._insp_field(surf, ix, fy, "y", lambda: str(obj[1]), lambda v: obj.__setitem__(1, int(v) if v.lstrip("-").isdigit() else obj[1]))
            fy = self._insp_field(surf, ix, fy, "w", lambda: str(obj[2]), lambda v: obj.__setitem__(2, max(8, int(v)) if v.isdigit() else obj[2]))
            fy = self._insp_field(surf, ix, fy, "h", lambda: str(obj[3]), lambda v: obj.__setitem__(3, max(8, int(v)) if v.isdigit() else obj[3]))
            fy = self._insp_field(surf, ix, fy, "label", lambda: obj[4] if len(obj) > 4 else "",
                                  lambda v: obj.__setitem__(4, v) if len(obj) > 4 else obj.append(v))

        btn_y = H - 56
        btn_w = (INSPECTOR_W - 28) // 2
        r_btn = pygame.Rect(ix + 8, btn_y, btn_w, 28)
        d_btn = pygame.Rect(ix + 14 + btn_w, btn_y, btn_w, 28)
        pygame.draw.rect(surf, C_INPUT_BG, r_btn, border_radius=4)
        pygame.draw.rect(surf, C_INPUT_BORD, r_btn, 1, border_radius=4)
        pygame.draw.rect(surf, C_INPUT_BG, d_btn, border_radius=4)
        pygame.draw.rect(surf, (80, 30, 30), d_btn, 1, border_radius=4)
        rs = TINY.render("Rename (F2)", True, C_ACCENT)
        ds_s = TINY.render("Delete (Del)", True, C_ENEMY)
        surf.blit(rs, (r_btn.x + (btn_w - rs.get_width()) // 2, r_btn.y + 7))
        surf.blit(ds_s, (d_btn.x + (btn_w - ds_s.get_width()) // 2, d_btn.y + 7))
        self._rename_btn = r_btn
        self._delete_btn = d_btn

    def _insp_field(self, surf, ix, fy, label, getter, setter):
        af = self._active_field
        fid = label
        lbl_s = TINY.render(label.upper(), True, C_MUTED)
        surf.blit(lbl_s, (ix + 12, fy))
        fy += lbl_s.get_height() + 3
        fr = pygame.Rect(ix + 8, fy, INSPECTOR_W - 16, 24)
        is_active = af is not None and af.get("id") == fid
        pygame.draw.rect(surf, C_INPUT_BG, fr, border_radius=3)
        pygame.draw.rect(surf, C_ACCENT if is_active else C_BORDER, fr, 1, border_radius=3)
        txt = af["text"] if is_active else getter()
        val_s = TINY.render(str(txt)[:22], True, C_TEXT)
        surf.blit(val_s, (fr.x + 6, fr.y + 5))
        if is_active and (pygame.time.get_ticks() // 500) % 2 == 0:
            cx = fr.x + 6 + val_s.get_width() + 1
            pygame.draw.line(surf, C_TEXT, (cx, fr.y + 4), (cx, fr.y + 18))
        self._inspector_fields.append((fr, getter, setter, fid))
        return fy + 32

    def _get_obj_x(self, obj):
        if isinstance(obj, dict):
            t = obj.get("type")
            if "position" in obj:
                return obj["position"][0]
            if t in ("trigger", "platform"):
                return obj.get("x", 0)
            if t == "spawn":
                return obj.get("pos_x", 0)
        elif isinstance(obj, list):
            return obj[0]
        return 0

    def _get_obj_y(self, obj):
        if isinstance(obj, dict):
            t = obj.get("type")
            if "position" in obj:
                return obj["position"][1]
            if t in ("trigger", "platform"):
                return obj.get("y", 0)
            if t == "spawn":
                return obj.get("pos_y", 0)
        elif isinstance(obj, list):
            return obj[1]
        return 0

    def _get_obj_w(self, obj):
        if isinstance(obj, dict):
            if obj.get("type") == "trigger":
                return obj.get("w", 0)
            if obj.get("type") == "platform":
                return obj.get("width", 0)
        elif isinstance(obj, list):
            return obj[2]
        return 0

    def _get_obj_h(self, obj):
        if isinstance(obj, dict):
            if obj.get("type") == "trigger":
                return obj.get("h", 0)
            if obj.get("type") == "platform":
                return obj.get("height", 0)
        elif isinstance(obj, list):
            return obj[3]
        return 0

    def _set_obj_x(self, obj, v):
        try:
            v = int(v)
        except Exception:
            return
        if isinstance(obj, dict):
            t = obj.get("type")
            if "position" in obj:
                obj["position"][0] = v
            elif t in ("trigger", "platform"):
                obj["x"] = v
            elif t == "spawn":
                obj["pos_x"] = v
        elif isinstance(obj, list):
            obj[0] = v

    def _set_obj_y(self, obj, v):
        try:
            v = int(v)
        except Exception:
            return
        if isinstance(obj, dict):
            t = obj.get("type")
            if "position" in obj:
                obj["position"][1] = v
            elif t in ("trigger", "platform"):
                obj["y"] = v
            elif t == "spawn":
                obj["pos_y"] = v
        elif isinstance(obj, list):
            obj[1] = v

    def _set_obj_w(self, obj, v):
        try:
            v = max(8, int(v))
        except Exception:
            return
        if isinstance(obj, dict):
            if obj.get("type") == "trigger":
                obj["w"] = v
            elif obj.get("type") == "platform":
                obj["width"] = v
        elif isinstance(obj, list):
            obj[2] = v

    def _set_obj_h(self, obj, v):
        try:
            v = max(8, int(v))
        except Exception:
            return
        if isinstance(obj, dict):
            if obj.get("type") == "trigger":
                obj["h"] = v
            elif obj.get("type") == "platform":
                obj["height"] = v
        elif isinstance(obj, list):
            obj[3] = v

    def draw_selection_overlay_big(self, surf):
        if not self.selected:
            return
        r = self._obj_rect(self.selected)
        if r is None:
            return
        x, y, w, h = r
        bx, by = self.world_to_big(x, y)
        rect = pygame.Rect(bx, by, w * SCALE, h * SCALE)
        pygame.draw.rect(surf, (20, 40, 90), rect.inflate(4, 4), 1, border_radius=2)
        pygame.draw.rect(surf, C_SEL_OUT, rect, 2, border_radius=2)
        hw = HANDLE_WLD * SCALE
        for cx, cy in self.corners_of(self.selected):
            hx, hy = self.world_to_big(cx, cy)
            hr = pygame.Rect(hx - hw // 2, hy - hw // 2, hw, hw)
            pygame.draw.rect(surf, (20, 25, 35), hr, border_radius=2)
            pygame.draw.rect(surf, C_HANDLE, hr, 2, border_radius=2)

    def draw_rename_popup(self, surf):
        if not self.naming or not self.selected:
            return
        r = self._obj_rect(self.selected)
        if r:
            bx, by = self.world_to_big(r[0], r[1])
        else:
            bx, by = surf.get_width() // 2, surf.get_height() // 2
        pw, ph = 280, 72
        px = max(self.toolbar_w() + 8, min(bx, self.inspector_x() - pw - 8))
        py = max(8, by - ph - 14)
        s = pygame.Surface((pw, ph), pygame.SRCALPHA)
        s.fill((*C_PANEL, 245))
        pygame.draw.rect(s, C_ACCENT, (0, 0, pw, ph), 1, border_radius=6)
        kind = self.selected.get("type", "wall") if isinstance(self.selected, dict) else "wall"
        cap = {"trigger": "name", "spawn": "came_from", "enemy": "name"}.get(kind, "label").upper()
        s.blit(TINY.render(cap, True, C_MUTED), (10, 8))
        inp_r = pygame.Rect(8, 24, pw - 16, 28)
        pygame.draw.rect(s, C_INPUT_BG, inp_r, border_radius=3)
        pygame.draw.rect(s, C_ACCENT, inp_r, 1, border_radius=3)
        val_s = BIG_SMALL.render(self.naming_text + ("_" if (pygame.time.get_ticks() // 500) % 2 == 0 else ""), True, C_TEXT)
        s.blit(val_s, (inp_r.x + 6, inp_r.y + 5))
        s.blit(TINY.render("Enter to confirm Â· Esc to cancel", True, C_MUTED), (10, 57))
        surf.blit(s, (px, py))

    def draw_level_prompt(self, surf):
        if not self.level_prompt_active:
            return
        pw, ph = 300, 64
        px = (surf.get_width() - pw) // 2
        py = (surf.get_height() - ph) // 2
        s = pygame.Surface((pw, ph), pygame.SRCALPHA)
        s.fill((*C_PANEL, 250))
        pygame.draw.rect(s, (100, 150, 255), (0, 0, pw, ph), 1, border_radius=6)
        s.blit(TINY.render("SWITCH TO LEVEL ID", True, C_MUTED), (10, 8))
        s.blit(BIG_FONT.render(self.level_prompt_text + "_", True, (100, 200, 255)), (10, 26))
        surf.blit(s, (px, py))

    def draw_hud(self, surf):
        mx, my = pygame.mouse.get_pos()
        wx, wy = self.screen_to_world(mx, my)
        lines = [
            (f"Level {self.current_level}", C_ACCENT),
            (f"x {wx}  y {wy}", C_MUTED),
            ("Tab=toolbar  Q=level  Del=remove  F2=rename", (50, 55, 70)),
        ]
        if self._dirty:
            lines.insert(2, ("â— unsaved", (180, 140, 60)))
        x0 = self.inspector_x() - 8
        y0 = 10
        for txt, col in lines:
            s = TINY.render(txt, True, col)
            surf.blit(s, (x0 - s.get_width(), y0))
            y0 += s.get_height() + 3

    def render_ui(self, surf):
        self.draw_toolbar(surf)
        self.draw_inspector(surf)
        self.draw_selection_overlay_big(surf)
        self.draw_rename_popup(surf)
        self.draw_level_prompt(surf)
        self.draw_hud(surf)

    def render(self, small_surf, big_surf):
        self.render_world(small_surf)
        big_surf.blit(pygame.transform.scale(small_surf, big_surf.get_size()), (0, 0))
        self.render_ui(big_surf)

    # â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _load_enemies_safe(self):
        try:
            self.world.load_enemies()
        except Exception as e:
            DPRINT("load_enemies error:", e)
        self._annotate_ids()

    def _delete_selected(self):
        sel = self.selected
        if sel is None:
            return
        ld = self.world.level_data
        removed = False
        if isinstance(sel, dict):
            t = sel.get("type")
            if "position" in sel:
                arr = ld.get("enemies", [])
            elif t == "trigger":
                arr = ld.get("triggers", [])
            elif t == "platform":
                arr = ld.get("platforms", [])
            elif t == "spawn":
                arr = ld.get("save_points", [])
            else:
                arr = []
            if sel in arr:
                arr.remove(sel)
                removed = True
        elif isinstance(sel, list):
            arr = ld.get("invis_walls", [])
            if sel in arr:
                arr.remove(sel)
                removed = True
        if removed:
            self.selected = None
            self._load_enemies_safe()
            self.mark_dirty()


def run():
    editor = Editor()
    running = True

    while running:
        dt = CLOCK.tick(60)

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                editor.save_world()
                running = False

            elif ev.type == pygame.MOUSEBUTTONDOWN:
                mx, my = ev.pos

                if ev.button == 1 and editor._rename_btn.collidepoint(mx, my) and editor.selected:
                    editor._open_rename(editor.selected)
                    continue
                if ev.button == 1 and editor._delete_btn.collidepoint(mx, my):
                    editor._delete_selected()
                    continue

                if ev.button == 1 and mx >= editor.inspector_x():
                    editor._inspector_click(mx, my)
                    continue

                if ev.button in (1, 2):
                    editor.handle_mouse_down(ev)
                elif ev.button == 3:
                    editor.drag_state = {"phase": "idle"}
                    editor.tool = "select"
                elif ev.button in (4, 5):
                    editor.handle_mouse_wheel(ev)

            elif ev.type == pygame.MOUSEBUTTONUP:
                if ev.button in (1, 2):
                    editor.handle_mouse_up(ev)

            elif ev.type == pygame.MOUSEMOTION:
                editor.handle_mouse_motion(ev)

            elif ev.type == pygame.MOUSEWHEEL:
                editor.handle_mouse_wheel(ev)

            elif ev.type == pygame.KEYDOWN:
                if editor._inspector_key(ev):
                    editor.mark_dirty()
                    continue

                if editor.naming:
                    if ev.key == pygame.K_RETURN:
                        editor._commit_naming()
                    elif ev.key == pygame.K_ESCAPE:
                        editor._cancel_naming()
                    elif ev.key == pygame.K_BACKSPACE:
                        editor.naming_text = editor.naming_text[:-1]
                    elif ev.unicode:
                        obj = editor.selected
                        if isinstance(obj, dict) and obj.get("type") == "spawn":
                            if ev.unicode.isdigit():
                                editor.naming_text += ev.unicode
                        else:
                            editor.naming_text += ev.unicode
                    continue

                if editor.level_prompt_active:
                    if ev.key == pygame.K_RETURN:
                        level_id = editor.level_prompt_text.strip()
                        if level_id:
                            editor.switch_level(level_id)
                        editor.level_prompt_active = False
                        editor.level_prompt_text = ""
                    elif ev.key == pygame.K_ESCAPE:
                        editor.level_prompt_active = False
                        editor.level_prompt_text = ""
                    elif ev.key == pygame.K_BACKSPACE:
                        editor.level_prompt_text = editor.level_prompt_text[:-1]
                    elif ev.unicode and ev.unicode.isprintable():
                        if not ev.unicode.isspace():
                            editor.level_prompt_text += ev.unicode
                    continue

                if ev.key == pygame.K_TAB:
                    editor.toolbar_visible = not editor.toolbar_visible
                elif ev.key == pygame.K_q:
                    editor.level_prompt_active = True
                    editor.level_prompt_text = ""
                elif ev.key == pygame.K_F2 and editor.selected:
                    editor._open_rename(editor.selected)
                elif ev.key in (pygame.K_DELETE, pygame.K_x):
                    editor._delete_selected()
                elif ev.key == pygame.K_F5:
                    editor.save_world()
                elif ev.key == pygame.K_d and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                    editor.debug_pick = not editor.debug_pick
                    DPRINT("Debug pick:", editor.debug_pick)

        editor.update(dt)
        editor.render(SCREEN_SURF, BIG_SCREEN)
        pygame.display.flip()

    editor.save_world()
    pygame.quit()


if __name__ == "__main__":
    run()

