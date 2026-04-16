"""
DrawWorld editor (rewritten + save_points support + UI on 720p)

This is the updated full file with the UI no longer unnecessarily zoomed:
- World still renders to 320x180 and is scaled to 1280x720.
- UI (toolbar, popups, status, prompts) is drawn directly on the 1280x720 surface
  and is NOT scaled by SCALE.
- Fonts, icons and popup sizes are normal-sized for 1280x720.
- Mouse -> world conversions still account for SCALE.
"""
import os
import pygame
import json
from pathlib import Path
from assetsLoader import Loader
from worlds.world_loader import World_loader
import uuid
import math
import sprites.Player.Player

pygame.init()
BIG_SCREEN = pygame.display.set_mode((1280, 720))
SCREEN = (320, 180)
SCREEN_SURF = pygame.Surface(SCREEN)

CLOCK = pygame.time.Clock()
FONT = pygame.font.SysFont("consolas", 16)
SMALL = pygame.font.SysFont("consolas", 14)

# SCALE is used only for converting between the world (320x180) and the window (1280x720)
SCALE = BIG_SCREEN.get_width() // SCREEN[0]  # expected 4

# UI fonts should NOT be scaled by SCALE
BIG_FONT = pygame.font.SysFont("consolas", 24)
BIG_SMALL = pygame.font.SysFont("consolas", 18)

# Config
TOOLBAR_W = 260  # toolbar width on big screen (pixels)
ICON_SIZE = 48  # base icon size (icons are kept at this pixel size in the UI)
HANDLE = 12
PICK_TOL = 40
DRAG_THRESHOLD = 6
DOUBLE_CLICK_MS = 300
SAVE_PATH = Path("worlds") / "level-spec.json"
CAM_KEY_SPEED = 800

def DPRINT(*a, **k):
    print("[DrawWorld]", *a, **k)


class ToolbarItem:
    def __init__(self, name, icon_surf, kind="enemy"):
        self.name = name
        self.icon = icon_surf
        self.kind = kind
        # rect in big-screen coordinates (for click)
        self.rect_big = pygame.Rect(0, 0, 0, 0)


def blit_renderer_to_screen(screen, renderer):
    """
    Keep as fallback; not used in main loop anymore but kept for safety.
    """
    try:
        scaled = pygame.transform.scale(renderer, (1280, 720))
        screen.blit(scaled, (0, 0))
    except Exception:
        try:
            w, h = renderer.get_size()
            screen.fill((0, 0, 0))
            screen.blit(renderer, ((1280 - w) // 2, (720 - h) // 2))
        except Exception:
            pass
    pygame.display.flip()


class Editor:
    def __init__(self):
        player = sprites.Player.Player.Player()
        self.world = World_loader(SCREEN, player)
        self.current_level = self.world.current_level

        # ensure level_data exists and required arrays
        self.world.level_data.setdefault("enemies", [])
        self.world.level_data.setdefault("triggers", [])
        self.world.level_data.setdefault("invis_walls", [])
        # NEW: platforms collection
        self.world.level_data.setdefault("platforms", [])
        # NEW: save_points collection (multiple spawn points)
        self.world.level_data.setdefault("save_points", [])

        self.toolbar_items = []
        self._build_toolbar()

        # Interaction state
        self.tool = "select"  # or 'enemy', 'trigger', 'wall', 'platform', 'spawn'
        self.placing_item = None
        self.placing_start = None
        self.potential_drag = None
        self.active_drag = None
        self.resizing = None
        self.selected = None
        self.naming = False
        self.naming_text = ""
        self.last_click_time = 0
        self.last_click_obj = None

        # level switching state
        self.level_prompt_active = False
        self.level_prompt_text = ""

        # toolbar UI state (big-screen pixels)
        self.toolbar_visible = True
        self.toolbar_scroll = 0

        # camera / panning state
        self.pan_active = False
        self.pan_start_mouse = (0, 0)
        self.pan_start_cam = (self.world.cam_x, self.world.cam_y)
        self.dt = 0

        # debug toggles
        self.debug_pick = False
        self._last_debug_click = None

    # ---------------- Toolbar ----------------
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
                                # keep icons at ICON_SIZE (UI not scaled)
                                icon = pygame.transform.smoothscale(surf, (ICON_SIZE, ICON_SIZE))
                                break
                            except Exception:
                                icon = None
                if icon is None:
                    icon = pygame.Surface((ICON_SIZE, ICON_SIZE), pygame.SRCALPHA)
                    icon.fill((150, 60, 60))
                self.toolbar_items.append(ToolbarItem(sub.name, icon, kind="enemy"))

        # Add trigger, wall and platform tools
        trig = pygame.Surface((ICON_SIZE, ICON_SIZE), pygame.SRCALPHA)
        trig.fill((220, 180, 30))
        wall = pygame.Surface((ICON_SIZE, ICON_SIZE), pygame.SRCALPHA)
        wall.fill((0, 150, 200))
        platform_icon = pygame.Surface((ICON_SIZE, ICON_SIZE), pygame.SRCALPHA)
        platform_icon.fill((80, 200, 120))
        self.toolbar_items.append(ToolbarItem("Trigger", trig, kind="trigger"))
        self.toolbar_items.append(ToolbarItem("Wall", wall, kind="wall"))
        self.toolbar_items.append(ToolbarItem("Platform", platform_icon, kind="platform"))

        # Spawn / save point tool (pink)
        spawn_icon = pygame.Surface((ICON_SIZE, ICON_SIZE), pygame.SRCALPHA)
        spawn_icon.fill((255, 80, 200))
        self.toolbar_items.append(ToolbarItem("Spawn", spawn_icon, kind="spawn"))

    # ---------------- Coordinate helpers ----------------
    def get_toolbar_width(self):
        return TOOLBAR_W if self.toolbar_visible else 0

    def clamp_toolbar_scroll(self):
        # toolbar_scroll is in big-screen pixels; item height uses ICON_SIZE (UI not scaled)
        item_h = ICON_SIZE + 16
        total_h = len(self.toolbar_items) * item_h
        max_scroll = max(0, total_h - (BIG_SCREEN.get_height() - 24))
        if self.toolbar_scroll < 0:
            self.toolbar_scroll = 0
        if self.toolbar_scroll > max_scroll:
            self.toolbar_scroll = max_scroll

    def screen_to_world(self, sx, sy):
        """
        Convert big-screen mouse coords -> world (world pixel coordinates used on the 320x180 surface).
        sx, sy are in big-screen coordinates (1280x720).
        """
        sx_small = sx // SCALE
        sy_small = sy // SCALE
        return sx_small + self.world.cam_x, sy_small + self.world.cam_y

    def world_to_screen(self, wx, wy):
        """
        Convert world coordinates -> world-surface screen coords (320x180 coordinate space).
        (This keeps coordinates relative to the small world surface.)
        """
        return wx - self.world.cam_x, wy - self.world.cam_y

    def world_to_big_screen(self, wx, wy):
        """
        Convert world coordinates -> big-screen pixel coordinates for UI drawing.
        """
        sx, sy = self.world_to_screen(wx, wy)
        return sx * SCALE, sy * SCALE

    # ---------------- Persistence ----------------
    def save_world(self):
        try:
            with open(SAVE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.world.world_data, f, indent=2)
            DPRINT("Saved world to", SAVE_PATH)
        except Exception as e:
            DPRINT("Save failed:", e)

    # ---------------- Picking / hit tests ----------------
    def corners_of_trigger(self, t):
        return [(t["x"], t["y"]), (t["x"] + t["w"], t["y"]), (t["x"], t["y"] + t["h"]), (t["x"] + t["w"], t["y"] + t["h"])]

    def corners_of_wall(self, w):
        if len(w) >= 4:
            x, y, wid, hei = w[0], w[1], w[2], w[3]
            return [(x, y), (x + wid, y), (x, y + hei), (x + wid, y + hei)]
        return []

    def corners_of_platform(self, p):
        return [(p["x"], p["y"]), (p["x"] + p["width"], p["y"]), (p["x"], p["y"] + p["height"]), (p["x"] + p["width"], p["y"] + p["height"])]

    def get_corner_hit_world(self, obj, mx_small, my_small):
        """
        mx_small, my_small are coordinates on the SMALL world surface (320x180).
        """
        if isinstance(obj, dict) and obj.get("type") == "trigger":
            for i, (cx, cy) in enumerate(self.corners_of_trigger(obj)):
                sx, sy = self.world_to_screen(cx, cy)
                if abs(mx_small - sx) <= HANDLE and abs(my_small - sy) <= HANDLE:
                    return i
        elif isinstance(obj, dict) and obj.get("type") == "platform":
            for i, (cx, cy) in enumerate(self.corners_of_platform(obj)):
                sx, sy = self.world_to_screen(cx, cy)
                if abs(mx_small - sx) <= HANDLE and abs(my_small - sy) <= HANDLE:
                    return i
        elif isinstance(obj, list):
            for i, (cx, cy) in enumerate(self.corners_of_wall(obj)):
                sx, sy = self.world_to_screen(cx, cy)
                if abs(mx_small - sx) <= HANDLE and abs(my_small - sy) <= HANDLE:
                    return i
        return None

    def pick_object_at_world(self, wx, wy):
        # Check enemies first
        for e in reversed(list(self.world.level_data.get("enemies", []))):
            pos = e.get("position")
            if not pos:
                continue
            ex, ey = pos
            if abs(wx - ex) <= PICK_TOL and abs(wy - ey) <= PICK_TOL:
                return e

        # triggers
        for t in reversed(list(self.world.level_data.get("triggers", []))):
            if (t["x"] - PICK_TOL) <= wx <= (t["x"] + t["w"] + PICK_TOL) and (t["y"] - PICK_TOL) <= wy <= (t["y"] + t["h"] + PICK_TOL):
                return t

        # platforms
        for p in reversed(list(self.world.level_data.get("platforms", []))):
            px = p.get("x", 0)
            py = p.get("y", 0)
            pw = p.get("width", 0)
            ph = p.get("height", 0)
            if (px - PICK_TOL) <= wx <= (px + pw + PICK_TOL) and (py - PICK_TOL) <= wy <= (py + ph + PICK_TOL):
                return p

        # save_points (spawn points) - treat as points
        for s in reversed(list(self.world.level_data.get("save_points", []))):
            sx = s.get("pos_x", 0)
            sy = s.get("pos_y", 0)
            if abs(wx - sx) <= PICK_TOL and abs(wy - sy) <= PICK_TOL:
                return s

        # invis walls
        for w in reversed(list(self.world.level_data.get("invis_walls", []))):
            if (w[0] - PICK_TOL) <= wx <= (w[0] + w[2] + PICK_TOL) and (w[1] - PICK_TOL) <= wy <= (w[1] + w[3] + PICK_TOL):
                return w

        # Fallback: live enemy instances mapping (unchanged)
        try:
            insts = getattr(self.world, 'enemies', None)
            if insts:
                for idx, inst in enumerate(insts):
                    ex = getattr(inst, 'world_x', None)
                    ey = getattr(inst, 'world_y', None)
                    if ex is None and hasattr(inst, 'pos'):
                        p = getattr(inst, 'pos')
                        if p:
                            ex, ey = p[0], p[1]
                    if ex is None or ey is None:
                        continue
                    if abs(wx - ex) <= PICK_TOL and abs(wy - ey) <= PICK_TOL:
                        matched = None
                        enemies = self.world.level_data.get('enemies', [])
                        for e in reversed(enemies):
                            if not isinstance(e, dict):
                                continue
                            pos = e.get('position')
                            if pos and abs(pos[0] - ex) <= 4 and abs(pos[1] - ey) <= 4:
                                matched = e
                                break
                        if matched is None:
                            matched = self._find_matching_enemy_dict_for_instance(inst)
                        if matched is None:
                            try:
                                enemies = self.world.level_data.get('enemies', [])
                                if idx < len(enemies):
                                    matched = enemies[idx]
                            except Exception:
                                matched = None
                        if matched:
                            return matched
        except Exception:
            pass

        return None

    def _sync_enemy_instance(self, enemy_dict):
        try:
            enemies = self.world.level_data.get("enemies", [])
            target_id = enemy_dict.get("id") if isinstance(enemy_dict, dict) else None
            inst_to_update = None
            if hasattr(self.world, 'enemies'):
                if target_id is not None:
                    for inst in self.world.enemies:
                        if getattr(inst, 'id', None) == target_id:
                            inst_to_update = inst
                            break
                if inst_to_update is None:
                    best = (None, 1e9)
                    for inst in self.world.enemies:
                        ix = getattr(inst, 'world_x', None)
                        iy = getattr(inst, 'world_y', None)
                        if ix is None and hasattr(inst, 'pos'):
                            p = getattr(inst, 'pos')
                            if p:
                                ix, iy = p[0], p[1]
                        if ix is None or iy is None:
                            continue
                        ex, ey = None, None
                        if isinstance(enemy_dict, dict):
                            pos = enemy_dict.get('position')
                            if pos:
                                ex, ey = pos[0], pos[1]
                            else:
                                ex = enemy_dict.get('x')
                                ey = enemy_dict.get('y')
                        if ex is None or ey is None:
                            continue
                        d = math.hypot(ix - ex, iy - ey)
                        if d < best[1]:
                            best = (inst, d)
                    if best[0] and best[1] <= PICK_TOL * 2:
                        inst_to_update = best[0]
                if inst_to_update is not None:
                    pos = None
                    if isinstance(enemy_dict, dict):
                        pos = enemy_dict.get('position')
                    if pos and hasattr(inst_to_update, 'update_position'):
                        inst_to_update.update_position(int(pos[0]), int(pos[1]))
        except Exception:
            pass

    def _find_matching_enemy_dict_for_instance(self, inst):
        try:
            enemies = self.world.level_data.get("enemies", [])
            ix = getattr(inst, 'world_x', None)
            iy = getattr(inst, 'world_y', None)
            if ix is None and hasattr(inst, 'pos'):
                p = getattr(inst, 'pos')
                if p:
                    ix, iy = p[0], p[1]
            if ix is None or iy is None:
                return None
            inst_type = None
            try:
                inst_type = inst.__class__.__name__.lower()
            except Exception:
                inst_type = None
            best = (None, 1e9)
            for e in enemies:
                ex = None
                ey = None
                if isinstance(e, dict):
                    pos = e.get('position')
                    if pos:
                        ex, ey = pos[0], pos[1]
                    else:
                        ex = e.get('x')
                        ey = e.get('y')
                if ex is None or ey is None:
                    continue
                d = math.hypot(ix - ex, iy - ey)
                score = d
                if inst_type and isinstance(e, dict):
                    if e.get('type') and e.get('type').lower() == inst_type:
                        score *= 0.5
                if score < best[1]:
                    best = (e, score)
            if best[0] and best[1] <= PICK_TOL * 2:
                return best[0]
        except Exception:
            pass
        return None

    def _annotate_instances_with_ids(self):
        try:
            enemies_data = self.world.level_data.get("enemies", [])
            insts = getattr(self.world, 'enemies', [])
            for idx, inst in enumerate(insts):
                if idx < len(enemies_data):
                    e_dict = enemies_data[idx]
                    if isinstance(e_dict, dict) and 'id' in e_dict:
                        inst.id = e_dict['id']
        except Exception:
            pass

    def switch_level(self, level_num):
        try:
            # Save current level first
            self.save_world()

            level_key = f"level_{level_num}"
            if level_key not in self.world.world_data:
                self.world.world_data[level_key] = {
                    "enemies": [], "triggers": [], "invis_walls": [], "platforms": [], "save_points": []
                }
                try:
                    self.save_world()
                except Exception:
                    pass

            self.current_level = level_num
            self.world.current_level = level_num
            self.world.level_data = self.world.world_data[level_key]
            self.world.level_data.setdefault("enemies", [])
            self.world.level_data.setdefault("triggers", [])
            self.world.level_data.setdefault("invis_walls", [])
            self.world.level_data.setdefault("platforms", [])
            self.world.level_data.setdefault("save_points", [])

            self.world.load_layers()
            self.world.build_collision_mask()
            self.world.load_enemies()

            self.world.cam_x = 0
            self.world.cam_y = 0
            self.selected = None
            self.potential_drag = None
            self.active_drag = None

            try:
                self._annotate_instances_with_ids()
            except Exception:
                pass

            DPRINT(f"Switched to level {level_num}")
        except Exception as e:
            DPRINT(f"Failed to switch to level {level_num}: {e}")

    # ---------------- Event handling ----------------
    def handle_mouse_down(self, ev):
        mx_big, my_big = ev.pos
        wx, wy = self.screen_to_world(mx_big, my_big)

        if self.debug_pick:
            try:
                DPRINT("DEBUG CLICK big_screen=", (mx_big, my_big), "world=", (wx, wy))
                for i, e in enumerate(self.world.level_data.get('enemies', [])):
                    if isinstance(e, dict):
                        DPRINT(f" lvl[{i}] type={e.get('type')} pos={e.get('position')}")
                    else:
                        DPRINT(f" lvl[{i}] raw={e}")
                insts = getattr(self.world, 'enemies', [])
                for i, inst in enumerate(insts):
                    ix = getattr(inst, 'world_x', None)
                    iy = getattr(inst, 'world_y', None)
                    if ix is None and hasattr(inst, 'pos'):
                        p = getattr(inst, 'pos')
                        if p:
                            ix, iy = p[0], p[1]
                    DPRINT(f" inst[{i}] class={inst.__class__.__name__} pos={(ix, iy)} id={getattr(inst, 'id', None)}")
                self._last_debug_click = ((mx_big, my_big), (wx, wy))
            except Exception:
                pass

        # toolbar click (big-screen coords)
        tw = self.get_toolbar_width()
        if tw and mx_big < tw:
            y_big = 12 - self.toolbar_scroll
            item_h_big = ICON_SIZE + 16
            for it in self.toolbar_items:
                r = pygame.Rect(12, y_big, tw - 24, ICON_SIZE)
                if r.collidepoint(mx_big, my_big):
                    # start a potential toolbar drag (store big coords)
                    self.potential_drag = {"obj": it, "mode": "toolbar_new", "start_mouse": (mx_big, my_big)}
                    return
                y_big += item_h_big

        # Placing new objects - when placing_item is chosen from toolbar (small world coords used internally)
        if self.tool in ("enemy", "trigger", "wall", "platform", "spawn") and self.placing_item:
            if self.tool == "enemy":
                new = {"type": self.placing_item.name, "position": [int(wx), int(wy)], "id": str(uuid.uuid4())}
                self.world.level_data.setdefault("enemies", []).append(new)
                self.save_world()
                self.world.load_enemies()
                try:
                    self._annotate_instances_with_ids()
                except Exception:
                    pass
                self.potential_drag = {"obj": new, "mode": "new", "start_mouse": (mx_big, my_big)}
                self.selected = new
                self.placing_item = None
                self.tool = "select"
                return

            if self.tool == "trigger":
                new = {"type": "trigger", "x": int(wx), "y": int(wy), "w": 96, "h": 56, "name": "", "id": str(uuid.uuid4())}
                self.world.level_data.setdefault("triggers", []).append(new)
                self.potential_drag = {"obj": new, "mode": "new", "start_mouse": (mx_big, my_big)}
                self.selected = new
                self.naming = True
                self.naming_text = ""
                DPRINT("Placed trigger at", (wx, wy))
                return

            if self.tool == "wall":
                new = [int(wx), int(wy), 96, 56, ""]
                self.world.level_data.setdefault("invis_walls", []).append(new)
                self.potential_drag = {"obj": new, "mode": "new", "start_mouse": (mx_big, my_big)}
                self.selected = new
                DPRINT("Placed wall at", (wx, wy))
                return

            if self.tool == "platform":
                new = {"type": "platform", "x": int(wx), "y": int(wy), "width": 128, "height": 20, "id": str(uuid.uuid4())}
                self.world.level_data.setdefault("platforms", []).append(new)
                self.potential_drag = {"obj": new, "mode": "new", "start_mouse": (mx_big, my_big)}
                self.selected = new
                DPRINT("Placed platform at", (wx, wy))
                return

            if self.tool == "spawn":
                new = {"type": "spawn", "came_from": 0, "pos_x": int(wx), "pos_y": int(wy), "id": str(uuid.uuid4())}
                self.world.level_data.setdefault("save_points", []).append(new)
                self.potential_drag = {"obj": new, "mode": "new", "start_mouse": (mx_big, my_big)}
                self.selected = new
                DPRINT("Placed spawn at", (wx, wy))
                return

        # Not placing: pick existing
        hit = self.pick_object_at_world(wx, wy)
        now = pygame.time.get_ticks()
        if hit and isinstance(hit, dict) and hit.get("type") in ("trigger", "spawn"):
            if self.last_click_obj is hit and (now - self.last_click_time) <= DOUBLE_CLICK_MS:
                # double-click begins naming (triggers) or editing came_from (spawn)
                self.naming = True
                if hit.get("type") == "trigger":
                    self.naming_text = hit.get("name", "")
                elif hit.get("type") == "spawn":
                    self.naming_text = str(hit.get("came_from", 0))
            self.last_click_time = now
            self.last_click_obj = hit

        # Middle mouse panning
        if hasattr(ev, 'button') and ev.button == 2:
            self.pan_active = True
            self.pan_start_mouse = (mx_big, my_big)
            self.pan_start_cam = (self.world.cam_x, self.world.cam_y)
            self.potential_drag = None
            self.active_drag = None
            return

        if hit:
            self.selected = hit
            # get corner hit: pass SMALL-surface coordinates
            mx_small, my_small = mx_big // SCALE, my_big // SCALE
            corner = self.get_corner_hit_world(hit, mx_small, my_small)
            DPRINT("pick hit", hit, "corner=", corner)
            if corner is not None:
                self.resizing = {"obj": hit, "corner": corner}
                self.potential_drag = None
                self.active_drag = None
            else:
                self.potential_drag = {"obj": hit, "mode": "existing", "start_mouse": (mx_big, my_big)}
                self.active_drag = None
        else:
            self.selected = None
            self.potential_drag = None
            self.active_drag = None

    def handle_mouse_up(self, ev):
        mx_big, my_big = ev.pos
        if hasattr(ev, 'button') and ev.button == 2:
            self.pan_active = False
            return

        # finalize toolbar drag placement if it never became active
        if self.potential_drag and self.potential_drag.get("mode") == "toolbar_new" and not self.active_drag:
            sx_big, sy_big = self.potential_drag.get("start_mouse", (mx_big, my_big))
            wx, wy = self.screen_to_world(mx_big, my_big)
            it = self.potential_drag["obj"]
            if it.kind == "enemy":
                new = {"type": it.name, "position": [int(wx), int(wy)], "id": str(uuid.uuid4())}
                self.world.level_data.setdefault("enemies", []).append(new)
                self.selected = new
            elif it.kind == "trigger":
                new = {"type": "trigger", "x": int(wx), "y": int(wy), "w": 96, "h": 56, "name": "", "id": str(uuid.uuid4())}
                self.world.level_data.setdefault("triggers", []).append(new)
                self.selected = new
            elif it.kind == "platform":
                new = {"type": "platform", "x": int(wx), "y": int(wy), "width": 128, "height": 20, "id": str(uuid.uuid4())}
                self.world.level_data.setdefault("platforms", []).append(new)
                self.selected = new
            elif it.kind == "spawn":
                new = {"type": "spawn", "came_from": 0, "pos_x": int(wx), "pos_y": int(wy), "id": str(uuid.uuid4())}
                self.world.level_data.setdefault("save_points", []).append(new)
                self.selected = new
            else:
                new = [int(wx), int(wy), 96, 56, ""]
                self.world.level_data.setdefault("invis_walls", []).append(new)
                self.selected = new
            self.save_world()
            try:
                self.world.load_enemies()
                try:
                    self._annotate_instances_with_ids()
                except Exception:
                    pass
            except Exception:
                pass
            self.potential_drag = None
            return

        if self.active_drag and self.active_drag.get("mode") == "new":
            obj = self.active_drag["obj"]
            if isinstance(obj, dict) and "position" in obj:
                self.save_world()
                self.world.load_enemies()
                try:
                    self._annotate_instances_with_ids()
                except Exception:
                    pass

        if self.resizing or self.active_drag:
            self.save_world()

        self.potential_drag = None
        self.active_drag = None
        self.resizing = None
        self.placing_start = None

    def handle_mouse_motion(self, ev):
        mx_big, my_big = ev.pos
        wx, wy = self.screen_to_world(mx_big, my_big)

        if self.pan_active:
            sx_big, sy_big = self.pan_start_mouse
            start_cx, start_cy = self.pan_start_cam
            dx = mx_big - sx_big
            dy = my_big - sy_big
            # moving mouse right pans camera left in world coords; convert by small pixels
            self.world.cam_x = int(start_cx - dx // SCALE)
            self.world.cam_y = int(start_cy - dy // SCALE)
            return

        # Start a drag if we moved beyond threshold (work in big-screen coords)
        if self.potential_drag and not self.active_drag:
            sx_big, sy_big = self.potential_drag["start_mouse"]
            if abs(mx_big - sx_big) > DRAG_THRESHOLD or abs(my_big - sy_big) > DRAG_THRESHOLD:
                obj = self.potential_drag["obj"]
                mode = self.potential_drag.get("mode")
                if mode == "existing":
                    if isinstance(obj, dict) and "position" in obj:
                        off = ( (wx - obj["position"][0]), (wy - obj["position"][1]) )
                    elif isinstance(obj, dict) and obj.get("type") == "trigger":
                        off = (wx - obj["x"], wy - obj["y"])
                    elif isinstance(obj, dict) and obj.get("type") == "platform":
                        off = (wx - obj["x"], wy - obj["y"])
                    elif isinstance(obj, dict) and obj.get("type") == "spawn":
                        off = (wx - obj["pos_x"], wy - obj["pos_y"])
                    elif isinstance(obj, list):
                        off = (wx - obj[0], wy - obj[1])
                    else:
                        off = (0, 0)
                    self.active_drag = {"obj": obj, "mode": "existing", "offset": off}
                elif mode == "toolbar_new":
                    it = obj  # ToolbarItem
                    if it.kind == "enemy":
                        new = {"type": it.name, "position": [int(wx), int(wy)], "id": str(uuid.uuid4())}
                        self.world.level_data.setdefault("enemies", []).append(new)
                        off = (0, 0)
                    elif it.kind == "trigger":
                        new = {"type": "trigger", "x": int(wx), "y": int(wy), "w": 96, "h": 56, "name": "", "id": str(uuid.uuid4())}
                        self.world.level_data.setdefault("triggers", []).append(new)
                        off = (new["w"] / 2, new["h"] / 2)
                    elif it.kind == "platform":
                        new = {"type": "platform", "x": int(wx), "y": int(wy), "width": 128, "height": 20, "id": str(uuid.uuid4())}
                        self.world.level_data.setdefault("platforms", []).append(new)
                        off = (new["width"] / 2, new["height"] / 2)
                    elif it.kind == "spawn":
                        new = {"type": "spawn", "came_from": 0, "pos_x": int(wx), "pos_y": int(wy), "id": str(uuid.uuid4())}
                        self.world.level_data.setdefault("save_points", []).append(new)
                        off = (0, 0)
                    else:
                        new = [int(wx), int(wy), 96, 56, ""]
                        self.world.level_data.setdefault("invis_walls", []).append(new)
                        off = (new[2] / 2, new[3] / 2)
                    self.selected = new
                    self.active_drag = {"obj": new, "mode": "new", "offset": off}
                else:
                    obj = self.potential_drag["obj"]
                    if isinstance(obj, dict) and "position" in obj:
                        off = (0, 0)
                    elif isinstance(obj, dict) and obj.get("type") == "trigger":
                        off = (obj["w"] / 2, obj["h"] / 2)
                    elif isinstance(obj, dict) and obj.get("type") == "platform":
                        off = (obj["width"] / 2, obj["height"] / 2)
                    elif isinstance(obj, dict) and obj.get("type") == "spawn":
                        off = (0, 0)
                    elif isinstance(obj, list):
                        off = (obj[2] / 2, obj[3] / 2)
                    else:
                        off = (0, 0)
                    self.active_drag = {"obj": obj, "mode": "new", "offset": off}

        # perform active drag
        if self.active_drag:
            obj = self.active_drag["obj"]
            offx, offy = self.active_drag.get("offset", (0, 0))
            if self.active_drag["mode"] == "existing":
                if isinstance(obj, dict) and "position" in obj:
                    obj["position"] = [int(wx - offx), int(wy - offy)]
                    try:
                        self._sync_enemy_instance(obj)
                    except Exception:
                        pass
                elif isinstance(obj, dict) and obj.get("type") == "trigger":
                    obj["x"] = int(wx - offx)
                    obj["y"] = int(wy - offy)
                elif isinstance(obj, dict) and obj.get("type") == "platform":
                    obj["x"] = int(wx - offx)
                    obj["y"] = int(wy - offy)
                elif isinstance(obj, dict) and obj.get("type") == "spawn":
                    obj["pos_x"] = int(wx - offx)
                    obj["pos_y"] = int(wy - offy)
                elif isinstance(obj, list):
                    obj[0] = int(wx - offx)
                    obj[1] = int(wy - offy)
            else:
                # new placement drag: update position/size
                if isinstance(obj, dict) and "position" in obj:
                    obj["position"] = [int(wx), int(wy)]
                elif isinstance(obj, dict) and obj.get("type") == "trigger":
                    sx_big, sy_big = self.potential_drag["start_mouse"]
                    start_wx, start_wy = self.screen_to_world(sx_big, sy_big)
                    obj["w"] = max(8, int(abs(wx - start_wx)))
                    obj["h"] = max(8, int(abs(wy - start_wy)))
                    obj["x"] = int(min(start_wx, wx))
                    obj["y"] = int(min(start_wy, wy))
                elif isinstance(obj, dict) and obj.get("type") == "platform":
                    sx_big, sy_big = self.potential_drag["start_mouse"]
                    start_wx, start_wy = self.screen_to_world(sx_big, sy_big)
                    obj["width"] = max(8, int(abs(wx - start_wx)))
                    obj["height"] = max(8, int(abs(wy - start_wy)))
                    obj["x"] = int(min(start_wx, wx))
                    obj["y"] = int(min(start_wy, wy))
                elif isinstance(obj, dict) and obj.get("type") == "spawn":
                    # spawn remains a point; allow dragging the point while creating new
                    obj["pos_x"] = int(wx)
                    obj["pos_y"] = int(wy)
                elif isinstance(obj, list):
                    sx_big, sy_big = self.potential_drag["start_mouse"]
                    start_wx, start_wy = self.screen_to_world(sx_big, sy_big)
                    obj[2] = max(8, int(abs(wx - start_wx)))
                    obj[3] = max(8, int(abs(wy - start_wy)))
                    obj[0] = int(min(start_wx, wx))
                    obj[1] = int(min(start_wy, wy))

        # perform resizing (mouse big coords -> map to small world coords)
        if self.resizing and self.resizing.get("obj"):
            obj = self.resizing["obj"]
            corner = self.resizing["corner"]
            # get small coords
            mx_small, my_small = mx_big // SCALE, my_big // SCALE
            wx_small, wy_small = mx_small + self.world.cam_x, my_small + self.world.cam_y
            if isinstance(obj, dict) and obj.get("type") == "trigger":
                if corner == 0:
                    brx = obj["x"] + obj["w"]
                    bry = obj["y"] + obj["h"]
                    obj["x"] = int(wx_small)
                    obj["y"] = int(wy_small)
                    obj["w"] = max(8, int(brx - obj["x"]))
                    obj["h"] = max(8, int(bry - obj["y"]))
                elif corner == 1:
                    blx = obj["x"]
                    bly = obj["y"] + obj["h"]
                    obj["y"] = int(wy_small)
                    obj["w"] = max(8, int((mx_small + self.world.cam_x) - obj["x"]))
                    obj["h"] = max(8, int(bly - obj["y"]))
                elif corner == 2:
                    trx = obj["x"] + obj["w"]
                    obj["x"] = int(wx_small)
                    obj["w"] = max(8, int(trx - obj["x"]))
                    obj["h"] = max(8, int((my_small + self.world.cam_y) - obj["y"]))
                elif corner == 3:
                    obj["w"] = max(8, int((mx_small + self.world.cam_x) - obj["x"]))
                    obj["h"] = max(8, int((my_small + self.world.cam_y) - obj["y"]))
            elif isinstance(obj, dict) and obj.get("type") == "platform":
                if corner == 0:
                    brx = obj["x"] + obj["width"]
                    bry = obj["y"] + obj["height"]
                    obj["x"] = int(wx_small)
                    obj["y"] = int(wy_small)
                    obj["width"] = max(8, int(brx - obj["x"]))
                    obj["height"] = max(8, int(bry - obj["y"]))
                elif corner == 1:
                    blx = obj["x"]
                    bly = obj["y"] + obj["height"]
                    obj["y"] = int(wy_small)
                    obj["width"] = max(8, int((mx_small + self.world.cam_x) - obj["x"]))
                    obj["height"] = max(8, int(bly - obj["y"]))
                elif corner == 2:
                    trx = obj["x"] + obj["width"]
                    obj["x"] = int(wx_small)
                    obj["width"] = max(8, int(trx - obj["x"]))
                    obj["height"] = max(8, int((my_small + self.world.cam_y) - obj["y"]))
                elif corner == 3:
                    obj["width"] = max(8, int((mx_small + self.world.cam_x) - obj["x"]))
                    obj["height"] = max(8, int((my_small + self.world.cam_y) - obj["y"]))
            elif isinstance(obj, list):
                if corner == 0:
                    brx = obj[0] + obj[2]
                    bry = obj[1] + obj[3]
                    obj[0] = int(mx_small + self.world.cam_x)
                    obj[1] = int(my_small + self.world.cam_y)
                    obj[2] = max(8, int(brx - obj[0]))
                    obj[3] = max(8, int(bry - obj[1]))
                elif corner == 1:
                    blx = obj[0]
                    bly = obj[1] + obj[3]
                    obj[1] = int(my_small + self.world.cam_y)
                    obj[2] = max(8, int((mx_small + self.world.cam_x) - obj[0]))
                    obj[3] = max(8, int(bly - obj[1]))
                elif corner == 2:
                    trx = obj[0] + obj[2]
                    obj[0] = int(mx_small + self.world.cam_x)
                    obj[2] = max(8, int(trx - obj[0]))
                    obj[3] = max(8, int((my_small + self.world.cam_y) - obj[1]))
                elif corner == 3:
                    obj[2] = max(8, int((mx_small + self.world.cam_x) - obj[0]))
                    obj[3] = max(8, int((my_small + self.world.cam_y) - obj[1]))

    def handle_mouse_wheel(self, ev):
        mx_big, my_big = pygame.mouse.get_pos()
        tw = self.get_toolbar_width()
        if not tw or mx_big > tw:
            return
        delta = 0
        if hasattr(ev, 'y'):
            delta = ev.y
        elif hasattr(ev, 'button'):
            if ev.button == 4:
                delta = 1
            elif ev.button == 5:
                delta = -1
        # scroll in big-screen pixels (UI units, not scaled)
        self.toolbar_scroll -= int(delta * (ICON_SIZE // 2))
        self.clamp_toolbar_scroll()

    def update(self, dt):
        self.dt = dt
        keys = pygame.key.get_pressed()
        speed = CAM_KEY_SPEED * (dt / 1000.0)
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.world.cam_x -= int(speed)
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.world.cam_x += int(speed)
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            self.world.cam_y -= int(speed)
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            self.world.cam_y += int(speed)
        self.clamp_toolbar_scroll()

    # ---------------- Drawing (world-side: small surface) ----------------
    def draw_handles(self, surf, obj):
        if isinstance(obj, dict) and obj.get("type") == "trigger":
            for cx, cy in self.corners_of_trigger(obj):
                sx, sy = self.world_to_screen(cx, cy)
                pygame.draw.rect(surf, (255, 200, 0), (int(sx - HANDLE // 2), int(sy - HANDLE // 2), HANDLE, HANDLE))
        elif isinstance(obj, dict) and obj.get("type") == "platform":
            for cx, cy in self.corners_of_platform(obj):
                sx, sy = self.world_to_screen(cx, cy)
                pygame.draw.rect(surf, (255, 200, 0), (int(sx - HANDLE // 2), int(sy - HANDLE // 2), HANDLE, HANDLE))
        elif isinstance(obj, list):
            for cx, cy in self.corners_of_wall(obj):
                sx, sy = self.world_to_screen(cx, cy)
                pygame.draw.rect(surf, (255, 200, 0), (int(sx - HANDLE // 2), int(sy - HANDLE // 2), HANDLE, HANDLE))
        elif isinstance(obj, dict) and obj.get("type") == "spawn":
            sx, sy = self.world_to_screen(obj["pos_x"], obj["pos_y"])
            pygame.draw.circle(surf, (255, 80, 200), (int(sx), int(sy)), 8)

    def draw_level_objects(self, surf):
        # invis walls
        for w in self.world.level_data.get("invis_walls", []):
            sx, sy = self.world_to_screen(w[0], w[1])
            pygame.draw.rect(surf, (0, 160, 200), pygame.Rect(sx, sy, w[2], w[3]), 3)

        # platforms
        for p in self.world.level_data.get("platforms", []):
            px, py = p.get("x", 0), p.get("y", 0)
            pw, ph = p.get("width", 0), p.get("height", 0)
            sx, sy = self.world_to_screen(px, py)
            pygame.draw.rect(surf, (80, 180, 120), pygame.Rect(sx, sy, pw, ph))
            pygame.draw.rect(surf, (20, 90, 50), pygame.Rect(sx, sy, pw, ph), 2)

        # triggers
        for t in self.world.level_data.get("triggers", []):
            sx, sy = self.world_to_screen(t["x"], t["y"])
            pygame.draw.rect(surf, (220, 180, 30), pygame.Rect(sx, sy, t["w"], t["h"]), 3)
            nm = t.get("name", "")
            if nm:
                surf.blit(SMALL.render(nm, True, (220, 180, 30)), (sx, sy - 18))

        # save_points (spawn points)
        for s in self.world.level_data.get("save_points", []):
            sx, sy = self.world_to_screen(s.get("pos_x", 0), s.get("pos_y", 0))
            pygame.draw.circle(surf, (255, 80, 200), (int(sx), int(sy)), 8)
            label = SMALL.render(f"FROM {s.get('came_from', 0)}", True, (255, 80, 200))
            surf.blit(label, (int(sx) + 12, int(sy) - 8))

        # enemies (World_loader draws enemies; world.draw_world is called in render_world)

    def render_world(self, surf):
        """
        Draw only the world (to the small SURF).
        """
        surf.fill((30, 30, 36))

        player_x = self.world.cam_x + SCREEN[0] // 2
        player_y = self.world.cam_y + SCREEN[1] // 2
        orig_update = self.world.update_camera

        def _clamp(px, py):
            self.world.cam_x = max(0, min(self.world.cam_x, getattr(self.world, 'max_cam_x', self.world.cam_x)))
            self.world.cam_y = max(0, min(self.world.cam_y, getattr(self.world, 'max_cam_y', self.world.cam_y)))

        self.world.update_camera = _clamp
        try:
            self.world.draw_world(surf, player_x, player_y)
        finally:
            self.world.update_camera = orig_update

        self.draw_level_objects(surf)

        if self.selected:
            # draw handles on small surface; they will be scaled up visually
            self.draw_handles(surf, self.selected)

    # ---------------- Drawing (UI on BIG_SCREEN) ----------------
    def draw_toolbar_big(self, surf):
        if not self.toolbar_visible:
            return
        tw = self.get_toolbar_width()
        h_big = surf.get_height()
        pygame.draw.rect(surf, (28, 30, 34), (0, 0, tw, h_big))
        x = 12
        y = 12 - self.toolbar_scroll
        item_h_big = ICON_SIZE + 16
        for it in self.toolbar_items:
            # icons are not scaled for the UI
            try:
                big_icon = it.icon
            except Exception:
                big_icon = pygame.Surface((ICON_SIZE, ICON_SIZE), pygame.SRCALPHA)
                big_icon.fill((120, 120, 120))
            surf.blit(big_icon, (x, y))
            label = BIG_SMALL.render(it.name, True, (220, 220, 220))
            surf.blit(label, (x + ICON_SIZE + 8, y + ICON_SIZE // 2 - label.get_height() // 2))
            it.rect_big = pygame.Rect(12, y, tw - 24, ICON_SIZE)
            y += item_h_big
        tool_label = BIG_SMALL.render(f"Tool: {self.tool}", True, (200, 200, 200))
        surf.blit(tool_label, (12, h_big - 28))

    def draw_name_popup_big(self, surf):
        # draws centered popup on BIG_SCREEN (UI units, not scaled)
        w_big, h_big = 420, 64
        x = (surf.get_width() - w_big) // 2
        y = (surf.get_height() - h_big) // 2
        s = pygame.Surface((w_big, h_big), pygame.SRCALPHA)
        s.fill((10, 10, 10, 220))
        pygame.draw.rect(s, (200, 200, 200), (0, 0, w_big, h_big), 2)
        if self.selected and isinstance(self.selected, dict) and self.selected.get("type") == "trigger":
            label = BIG_FONT.render("Name: " + self.naming_text, True, (240, 240, 240))
        elif self.selected and isinstance(self.selected, dict) and self.selected.get("type") == "spawn":
            label = BIG_FONT.render("came_from: " + self.naming_text, True, (240, 240, 240))
        else:
            label = BIG_FONT.render(self.naming_text, True, (240, 240, 240))
        s.blit(label, (12, h_big // 2 - label.get_height() // 2))
        surf.blit(s, (x, y))

    def draw_level_prompt_big(self, surf):
        w_big, h_big = 420, 64
        x = (surf.get_width() - w_big) // 2
        y = (surf.get_height() - h_big) // 2
        s = pygame.Surface((w_big, h_big), pygame.SRCALPHA)
        s.fill((10, 10, 10, 220))
        pygame.draw.rect(s, (100, 150, 255), (0, 0, w_big, h_big), 2)
        label = BIG_FONT.render("Level #: " + self.level_prompt_text, True, (100, 200, 255))
        s.blit(label, (12, h_big // 2 - label.get_height() // 2))
        surf.blit(s, (x, y))

    def render_ui(self, surf):
        """
        Draw toolbar, popups, status line and other UI directly to the big 1280x720 surface.
        """
        # Draw toolbar (on the left)
        self.draw_toolbar_big(surf)

        # status line (big-screen coords)
        sel_label = "None"
        if self.selected:
            if isinstance(self.selected, dict):
                if self.selected.get("type") == "spawn":
                    sel_label = f"Spawn(from={self.selected.get('came_from',0)})"
                else:
                    sel_label = str(self.selected.get("type", "dict"))
            elif isinstance(self.selected, list):
                sel_label = "Wall"
            else:
                sel_label = str(self.selected)
        status = BIG_SMALL.render(f"Selected: {sel_label}", True, (200, 200, 200))
        surf.blit(status, (self.get_toolbar_width() + 8, 8))

        level_label = BIG_SMALL.render(f"Level: {self.current_level} | Press Q to switch", True, (150, 200, 255))
        surf.blit(level_label, (self.get_toolbar_width() + 8, 32))

        # Draw name popup / prompt if active
        if self.naming:
            self.draw_name_popup_big(surf)

        if self.level_prompt_active:
            self.draw_level_prompt_big(surf)

    # ---------------- Orchestrating render ----------------
    def render(self, small_surf, big_surf):
        """
        High-level render function called from main loop.
        - Draw world to small_surf
        - Scale small_surf into big_surf (blit)
        - Draw UI on top of big_surf
        """
        # 1) draw world onto small surface
        self.render_world(small_surf)

        # 2) scale world surface up and blit to full screen
        scaled_world = pygame.transform.scale(small_surf, big_surf.get_size())
        big_surf.blit(scaled_world, (0, 0))

        # 3) draw UI elements on big surface
        self.render_ui(big_surf)

# ---------------- Main loop helpers ----------------
def run():
    editor = Editor()
    running = True
    while running:
        dt = CLOCK.tick(60)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.MOUSEBUTTONDOWN:
                if ev.button == 1:
                    editor.handle_mouse_down(ev)
                elif ev.button == 2:
                    editor.handle_mouse_down(ev)
                elif ev.button == 3:
                    editor.placing_item = None
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
                # debug toggle
                if ev.key == pygame.K_d:
                    editor.debug_pick = not editor.debug_pick
                    DPRINT("Debug pick:", editor.debug_pick)
                    continue
                # toggle toolbar
                if ev.key == pygame.K_TAB:
                    editor.toolbar_visible = not editor.toolbar_visible
                    DPRINT("Toolbar visible:", editor.toolbar_visible)
                    continue
                # level switching prompt (Q key)
                if ev.key == pygame.K_q and not editor.naming:
                    editor.level_prompt_active = True
                    editor.level_prompt_text = ""
                    continue

                # delete selected with Delete or X
                if ev.key in (pygame.K_DELETE, pygame.K_x) and not editor.naming:
                    if editor.selected:
                        sel = editor.selected
                        removed = False
                        if isinstance(sel, dict) and "position" in sel:
                            arr = editor.world.level_data.get("enemies", [])
                            if sel in arr:
                                arr.remove(sel)
                                removed = True
                        elif isinstance(sel, dict) and sel.get("type") == "trigger":
                            arr = editor.world.level_data.get("triggers", [])
                            if sel in arr:
                                arr.remove(sel)
                                removed = True
                        elif isinstance(sel, dict) and sel.get("type") == "platform":
                            arr = editor.world.level_data.get("platforms", [])
                            if sel in arr:
                                arr.remove(sel)
                                removed = True
                        elif isinstance(sel, dict) and sel.get("type") == "spawn":
                            arr = editor.world.level_data.get("save_points", [])
                            if sel in arr:
                                arr.remove(sel)
                                removed = True
                        elif isinstance(sel, list):
                            arr = editor.world.level_data.get("invis_walls", [])
                            if sel in arr:
                                arr.remove(sel)
                                removed = True
                        if removed:
                            editor.selected = None
                            editor.save_world()
                            try:
                                editor.world.load_enemies()
                                try:
                                    editor._annotate_instances_with_ids()
                                except Exception:
                                    pass
                            except Exception:
                                pass
                            DPRINT("Deleted selected")
                    continue

                # start renaming via F2
                if ev.key == pygame.K_F2 and not editor.naming and editor.selected:
                    editor.naming = True
                    if isinstance(editor.selected, dict):
                        if editor.selected.get("type") == "trigger":
                            editor.naming_text = editor.selected.get("name", "")
                        elif editor.selected.get("type") == "spawn":
                            editor.naming_text = str(editor.selected.get("came_from", 0))
                        else:
                            editor.naming_text = editor.selected.get("name", "")
                    elif isinstance(editor.selected, list) and len(editor.selected) >= 5:
                        editor.naming_text = editor.selected[4] or ""
                    else:
                        editor.naming_text = ""
                    continue

                # naming input handling
                if editor.naming:
                    # Enter to commit
                    if ev.key == pygame.K_RETURN:
                        text = editor.naming_text.strip()
                        if isinstance(editor.selected, dict) and editor.selected.get("type") == "trigger":
                            editor.selected["name"] = text or ""
                        elif isinstance(editor.selected, dict) and editor.selected.get("type") == "spawn":
                            try:
                                came = int(text) if text != "" else 0
                            except ValueError:
                                came = 0
                            editor.selected["came_from"] = came
                        elif isinstance(editor.selected, dict) and "position" in editor.selected:
                            editor.selected["name"] = text
                        elif isinstance(editor.selected, list):
                            if len(editor.selected) >= 5:
                                editor.selected[4] = text
                            else:
                                while len(editor.selected) < 5:
                                    editor.selected.append("")
                                editor.selected[4] = text
                        editor.naming = False
                        editor.save_world()
                        DPRINT("Renamed/edited to", text)
                    elif ev.key == pygame.K_ESCAPE:
                        editor.naming = False
                    else:
                        # accept digit keys for came_from (for spawn) and general characters
                        if isinstance(editor.selected, dict) and editor.selected.get("type") == "spawn":
                            # allow digits and backspace
                            if len(ev.unicode) > 0 and ev.unicode.isdigit():
                                editor.naming_text += ev.unicode
                            elif ev.key == pygame.K_BACKSPACE:
                                editor.naming_text = editor.naming_text[:-1]
                        else:
                            if ev.key == pygame.K_BACKSPACE:
                                editor.naming_text = editor.naming_text[:-1]
                            elif len(ev.unicode) > 0:
                                editor.naming_text += ev.unicode

                # level prompt handling
                if editor.level_prompt_active:
                    if ev.key == pygame.K_RETURN:
                        try:
                            level_num = int(editor.level_prompt_text.strip())
                            if True:
                                editor.switch_level(level_num)
                                editor.level_prompt_active = False
                                editor.level_prompt_text = ""
                                DPRINT(f"Switched to level {level_num}")
                            else:
                                DPRINT("Level must be >= 1")
                        except ValueError:
                            DPRINT("Invalid level number")
                        else:
                            editor.level_prompt_active = False
                            editor.level_prompt_text = ""
                    elif ev.key == pygame.K_ESCAPE:
                        editor.level_prompt_active = False
                        editor.level_prompt_text = ""
                    else:
                        if len(ev.unicode) > 0 and ev.unicode.isdigit():
                            editor.level_prompt_text += ev.unicode
                        elif ev.key == pygame.K_BACKSPACE:
                            editor.level_prompt_text = editor.level_prompt_text[:-1]

        editor.update(dt)

        # render pipeline: world -> small surface; scale to big surface; UI on big surface
        editor.render(SCREEN_SURF, BIG_SCREEN)

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    run()