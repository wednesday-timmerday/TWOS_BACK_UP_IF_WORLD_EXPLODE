from __future__ import annotations

import copy
import json
import os
import re
import sys
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QBrush,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

try:
    from PIL import Image  # noqa: F401
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False


MAGENTA = QColor(255, 0, 255)
GRID_COLOR = QColor(255, 255, 255, 40)
HOVER_COLOR = QColor(80, 160, 255, 90)
SELECTED_BORDER = QColor(90, 170, 255)
CHECKER_LIGHT = QColor(58, 58, 64)
CHECKER_DARK = QColor(48, 48, 54)
CHECKER_SIZE = 16
MIN_ZOOM = 0.05
MAX_ZOOM = 32.0
ZOOM_STEP = 1.15
MISSING_TILE = -1
AUTO_GROUP_SIZE = 16
TILE_PACK_SHIFT = 20
TILE_PACK_MASK = (1 << TILE_PACK_SHIFT) - 1


class WorldParseError(Exception):
    pass



class ToolType(Enum):
    PENCIL = auto()
    BUCKET = auto()


@dataclass
class EditorObject:
    kind: str
    x: int
    y: int
    w: int = 0
    h: int = 0
    name: str = ""
    came_from: int = 0
    obj_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def is_point(self) -> bool:
        return self.kind in {"enemy", "spawn"}

    def copy(self) -> "EditorObject":
        return EditorObject(**asdict(self))
@dataclass
class Layer:
    name: str
    tiles: List[int]
    visible: bool = True


@dataclass
class World:
    image_names: List[str]
    tile_w: int
    tile_h: int
    world_w: int
    world_h: int
    layers: List[Layer] = field(default_factory=list)
    objects: List[EditorObject] = field(default_factory=list)
    source_path: Optional[str] = None
    tileset_paths: List[Optional[str]] = field(default_factory=list)
    objects_path: Optional[str] = None

    @property
    def image_name(self) -> str:
        return self.image_names[0] if self.image_names else ""

    @image_name.setter
    def image_name(self, value: str) -> None:
        self.image_names = [value] if value else []

    def tile_count(self) -> int:
        return self.world_w * self.world_h

    def get_tile(self, layer_index: int, tx: int, ty: int) -> int:
        layer = self.layers[layer_index]
        return layer.tiles[ty * self.world_w + tx]

    def set_tile(self, layer_index: int, tx: int, ty: int, value: int) -> None:
        layer = self.layers[layer_index]
        layer.tiles[ty * self.world_w + tx] = value


class TileCodec:
    @staticmethod
    def encode(tileset_index: int, tile_index: int) -> int:
        if tileset_index < 0 or tile_index < 0:
            return MISSING_TILE
        return ((tileset_index + 1) << TILE_PACK_SHIFT) | (tile_index & TILE_PACK_MASK)

    @staticmethod
    def decode(value: int) -> Optional[Tuple[int, int]]:
        if value < 0:
            return None
        tileset_token = value >> TILE_PACK_SHIFT
        tile_index = value & TILE_PACK_MASK
        tileset_index = tileset_token - 1
        if tileset_index < 0:
            return None
        return tileset_index, tile_index

    @staticmethod
    def encode_text(tileset_index: int, tile_index: int) -> str:
        return f"${tileset_index + 1}A{tile_index}"

    @staticmethod
    def encode_missing_text() -> str:
        return "$0A0"


class WorldParser:
    @staticmethod
    def _parse_image_list(raw: str) -> List[str]:
        raw = raw.strip()
        if not raw:
            return []
        if raw.startswith("[") and raw.endswith("]"):
            raw = raw[1:-1].strip()
        if not raw:
            return []
        parts = [part.strip() for part in raw.split(",")]
        results: List[str] = []
        for part in parts:
            if not part:
                continue
            if (part.startswith('"') and part.endswith('"')) or (part.startswith("'") and part.endswith("'")):
                part = part[1:-1]
            results.append(part.strip())
        return results

    @staticmethod
    def parse(text: str) -> World:
        lines = text.splitlines()
        n = len(lines)
        i = 0
        header_map: Dict[str, str] = {}

        while i < n:
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            if line.upper().startswith("LAYER"):
                break
            if "=" in line:
                key, _, value = line.partition("=")
                header_map[key.strip().upper()] = value.strip()
            else:
                raise WorldParseError(f"Malformed header line: '{line}'")
            i += 1

        try:
            image_raw = header_map["IMAGE"]
            total_layers = int(header_map["TOTAL_LAYERS"])
            tile_w = int(header_map["TILE_W"])
            tile_h = int(header_map["TILE_H"])
            world_w = int(header_map["WORLD_W"])
            world_h = int(header_map["WORLD_H"])
        except KeyError as exc:
            raise WorldParseError(f"Missing required header field: {exc}") from exc
        except ValueError as exc:
            raise WorldParseError(f"Header field is not a valid integer: {exc}") from exc

        if tile_w <= 0 or tile_h <= 0:
            raise WorldParseError("TILE_W and TILE_H must be positive integers.")
        if world_w <= 0 or world_h <= 0:
            raise WorldParseError("WORLD_W and WORLD_H must be positive integers.")
        if total_layers <= 0:
            raise WorldParseError("TOTAL_LAYERS must be a positive integer.")

        image_names = WorldParser._parse_image_list(image_raw)
        if not image_names:
            image_names = [image_raw.strip().strip("[]")]

        expected = world_w * world_h
        layers: List[Layer] = []
        layer_index = 0

        while i < n and layer_index < total_layers:
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            if not line.upper().startswith("LAYER"):
                raise WorldParseError(f"Expected a LAYER declaration but found: '{line}'")

            colon_pos = line.find(":")
            if colon_pos == -1:
                raise WorldParseError(f"Malformed layer header (missing ':'): '{line}'")

            layer_name = line[:colon_pos].strip()
            trailing = line[colon_pos + 1 :]
            i += 1

            data_parts = [trailing]
            while i < n:
                nxt = lines[i].strip()
                if not nxt:
                    i += 1
                    continue
                if nxt.upper().startswith("LAYER"):
                    break
                data_parts.append(nxt)
                i += 1

            raw = "".join(data_parts)
            tiles = WorldParser._parse_tile_string(raw)
            if len(tiles) < expected:
                tiles = tiles + [MISSING_TILE] * (expected - len(tiles))
            elif len(tiles) > expected:
                tiles = tiles[:expected]

            layers.append(Layer(name=layer_name, tiles=tiles))
            layer_index += 1

        while layer_index < total_layers:
            layers.append(Layer(name=f"LAYER{layer_index + 1}", tiles=[MISSING_TILE] * expected))
            layer_index += 1

        if not layers:
            raise WorldParseError("World file does not contain any layer data.")

        return World(
            image_names=image_names,
            tile_w=tile_w,
            tile_h=tile_h,
            world_w=world_w,
            world_h=world_h,
            layers=layers,
        )

    @staticmethod
    def _parse_tile_string(raw: str) -> List[int]:
        raw = raw.replace(" ", "").replace("\t", "").replace("\r", "").replace("\n", "")
        if not raw:
            return []
        tiles: List[int] = []
        parts = raw.split("$")
        for part in parts:
            if not part:
                continue
            if "A" in part:
                left, _, right = part.partition("A")
                try:
                    tileset_num = int(left)
                    tile_index = int(right)
                except ValueError:
                    tiles.append(MISSING_TILE)
                    continue
                if tileset_num <= 0:
                    tiles.append(MISSING_TILE)
                else:
                    tiles.append(TileCodec.encode(tileset_num - 1, tile_index))
            else:
                try:
                    tiles.append(TileCodec.encode(0, int(part)))
                except ValueError:
                    tiles.append(MISSING_TILE)
        return tiles

    @staticmethod
    def serialize(world: World) -> str:
        lines = [
            f"IMAGE = [{', '.join(world.image_names)}]",
            f"TOTAL_LAYERS = {len(world.layers)}",
            f"TILE_W = {world.tile_w}",
            f"TILE_H = {world.tile_h}",
            f"WORLD_W = {world.world_w}",
            f"WORLD_H = {world.world_h}",
        ]
        for idx, layer in enumerate(world.layers, start=1):
            lines.append(f"LAYER{idx}:")
            encoded: List[str] = []
            for tile in layer.tiles:
                decoded = TileCodec.decode(tile)
                if decoded is None:
                    encoded.append(TileCodec.encode_missing_text())
                else:
                    encoded.append(TileCodec.encode_text(decoded[0], decoded[1]))
            lines.append("".join(encoded))
        return "\n".join(lines) + "\n"


class Tileset:
    def __init__(self, pixmap: Optional[QPixmap], tile_w: int, tile_h: int, source_path: Optional[str] = None):
        self.pixmap = pixmap
        self.tile_w = max(1, tile_w)
        self.tile_h = max(1, tile_h)
        self.source_path = source_path

    @property
    def valid(self) -> bool:
        return self.pixmap is not None and not self.pixmap.isNull()

    @property
    def columns(self) -> int:
        if not self.valid:
            return 0
        return max(1, self.pixmap.width() // self.tile_w)

    @property
    def rows(self) -> int:
        if not self.valid:
            return 0
        return max(1, self.pixmap.height() // self.tile_h)

    @property
    def tile_count(self) -> int:
        return self.columns * self.rows

    def source_rect(self, index: int) -> Optional[QRect]:
        if not self.valid or index < 0 or index >= self.tile_count:
            return None
        col = index % self.columns
        row = index // self.columns
        return QRect(col * self.tile_w, row * self.tile_h, self.tile_w, self.tile_h)


class MapView(QWidget):
    mouseTileChanged = Signal(object)
    zoomChanged = Signal(float)
    activeLayerModified = Signal()
    editCommitted = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.world: Optional[World] = None
        self.tilesets: List[Optional[Tileset]] = []
        self.active_layer_index: int = 0
        self.current_tool: ToolType = ToolType.PENCIL
        self.current_stamp: List[List[int]] = [[MISSING_TILE]]
        self.show_grid: bool = True
        self.auto_tile_enabled: bool = False

        self.zoom: float = 3.0
        self.offset = QPointF(0.0, 0.0)

        self._panning = False
        self._pan_last_pos = QPoint()
        self._painting = False
        self._hover_tile: Optional[Tuple[int, int]] = None
        self._last_stamp_origin: Optional[Tuple[int, int]] = None
        self._undo_stack: List[World] = []
        self._centered_once = False

    def set_world(self, world: Optional[World]) -> None:
        self.world = world
        self.active_layer_index = 0
        self._centered_once = False
        self._undo_stack.clear()
        if world is not None:
            self.center_view()
        self.update()

    def set_tilesets(self, tilesets: List[Optional[Tileset]]) -> None:
        self.tilesets = tilesets
        self.update()

    def set_current_stamp(self, stamp: List[List[int]]) -> None:
        if not stamp or not stamp[0]:
            self.current_stamp = [[MISSING_TILE]]
        else:
            self.current_stamp = [row[:] for row in stamp]

    def set_auto_tile_enabled(self, enabled: bool) -> None:
        self.auto_tile_enabled = enabled
        self.update()

    def center_view(self) -> None:
        if not self.world:
            return
        map_w = self.world.world_w * self.world.tile_w * self.zoom
        map_h = self.world.world_h * self.world.tile_h * self.zoom
        self.offset = QPointF((self.width() - map_w) / 2.0, (self.height() - map_h) / 2.0)
        self.update()

    def push_undo_state(self) -> None:
        if self.world is None:
            return
        self._undo_stack.append(copy.deepcopy(self.world))
        if len(self._undo_stack) > 64:
            self._undo_stack.pop(0)

    def undo(self) -> Optional[World]:
        if not self._undo_stack:
            return None
        restored = self._undo_stack.pop()
        self.set_world(restored)
        return restored

    def screen_to_tile(self, pos: QPointF) -> Optional[Tuple[int, int]]:
        if not self.world:
            return None
        tw = self.world.tile_w * self.zoom
        th = self.world.tile_h * self.zoom
        if tw <= 0 or th <= 0:
            return None
        wx = (pos.x() - self.offset.x()) / tw
        wy = (pos.y() - self.offset.y()) / th
        tx = int(wx) if wx >= 0 else int(wx) - 1
        ty = int(wy) if wy >= 0 else int(wy) - 1
        if 0 <= tx < self.world.world_w and 0 <= ty < self.world.world_h:
            return tx, ty
        return None

    def tile_screen_rect(self, tx: int, ty: int) -> QRectF:
        tw = self.world.tile_w * self.zoom
        th = self.world.tile_h * self.zoom
        return QRectF(self.offset.x() + tx * tw, self.offset.y() + ty * th, tw, th)

    def _draw_checkerboard(self, painter: QPainter) -> None:
        w = self.width()
        h = self.height()
        painter.fillRect(0, 0, w, h, CHECKER_DARK)
        cols = w // CHECKER_SIZE + 2
        rows = h // CHECKER_SIZE + 2
        painter.setPen(Qt.NoPen)
        for row in range(rows):
            for col in range(cols):
                if (row + col) % 2 == 0:
                    painter.fillRect(col * CHECKER_SIZE, row * CHECKER_SIZE, CHECKER_SIZE, CHECKER_SIZE, CHECKER_LIGHT)

    def _draw_tile(self, painter: QPainter, tile_value: int, rect: QRectF) -> None:
        decoded = TileCodec.decode(tile_value)
        if decoded is None:
            painter.fillRect(rect, MAGENTA)
            return
        tileset_index, tile_index = decoded
        if 0 <= tileset_index < len(self.tilesets):
            tileset = self.tilesets[tileset_index]
            if tileset is not None and tileset.valid:
                src = tileset.source_rect(tile_index)
                if src is not None:
                    painter.drawPixmap(rect, tileset.pixmap, QRectF(src))
                    return
        painter.fillRect(rect, MAGENTA)

    def _update_tile_rect(self, tx: int, ty: int) -> None:
        rect = self.tile_screen_rect(tx, ty)
        margin = 2
        self.update(rect.adjusted(-margin, -margin, margin, margin).toAlignedRect())

    def _apply_stamp(self, tx: int, ty: int) -> None:
        if self.world is None:
            return
        if not (0 <= self.active_layer_index < len(self.world.layers)):
            return

        changed: List[Tuple[int, int]] = []
        stamp_h = len(self.current_stamp)
        stamp_w = len(self.current_stamp[0]) if stamp_h else 0
        layer = self.world.layers[self.active_layer_index]

        for dy in range(stamp_h):
            for dx in range(stamp_w):
                mx = tx + dx
                my = ty + dy
                if not (0 <= mx < self.world.world_w and 0 <= my < self.world.world_h):
                    continue
                value = self.current_stamp[dy][dx]
                pos = my * self.world.world_w + mx
                if layer.tiles[pos] != value:
                    layer.tiles[pos] = value
                    changed.append((mx, my))

        if not changed:
            return
        self._retile_region(changed)
        self._update_dirty_from_points(changed, stamp_w, stamp_h)
        self.activeLayerModified.emit()

    def _paint_at(self, tx: int, ty: int) -> None:
        self._apply_stamp(tx, ty)

    def _flood_fill(self, tx: int, ty: int) -> None:
        if self.world is None:
            return
        if not (0 <= self.active_layer_index < len(self.world.layers)):
            return
        layer = self.world.layers[self.active_layer_index]
        ww, wh = self.world.world_w, self.world.world_h
        target = layer.tiles[ty * ww + tx]
        replacement = self.current_stamp[0][0] if self.current_stamp and self.current_stamp[0] else MISSING_TILE
        if target == replacement:
            return

        stack = [(tx, ty)]
        visited = bytearray(ww * wh)
        min_x, min_y, max_x, max_y = tx, ty, tx, ty
        changed = []

        while stack:
            cx, cy = stack.pop()
            pos = cy * ww + cx
            if visited[pos]:
                continue
            if layer.tiles[pos] != target:
                continue
            visited[pos] = 1
            layer.tiles[pos] = replacement
            changed.append((cx, cy))

            min_x = min(min_x, cx)
            max_x = max(max_x, cx)
            min_y = min(min_y, cy)
            max_y = max(max_y, cy)

            if cx > 0:
                stack.append((cx - 1, cy))
            if cx < ww - 1:
                stack.append((cx + 1, cy))
            if cy > 0:
                stack.append((cx, cy - 1))
            if cy < wh - 1:
                stack.append((cx, cy + 1))

        self._retile_region(changed)
        self._update_dirty_rect(min_x, min_y, max_x, max_y)
        self.activeLayerModified.emit()

    def _update_dirty_rect(self, min_x: int, min_y: int, max_x: int, max_y: int) -> None:
        top_left = self.tile_screen_rect(min_x, min_y).topLeft()
        bottom_right = self.tile_screen_rect(max_x, max_y).bottomRight()
        margin = 3
        dirty = QRectF(top_left, bottom_right).adjusted(-margin, -margin, margin, margin)
        self.update(dirty.toAlignedRect())

    def _update_dirty_from_points(self, points: List[Tuple[int, int]], width: int, height: int) -> None:
        min_x = min(p[0] for p in points)
        min_y = min(p[1] for p in points)
        max_x = max(p[0] for p in points) + max(0, width - 1)
        max_y = max(p[1] for p in points) + max(0, height - 1)
        self._update_dirty_rect(min_x, min_y, max_x, max_y)

    def _retile_region(self, changed: List[Tuple[int, int]]) -> None:
        if not self.auto_tile_enabled or self.world is None:
            return
        if not (0 <= self.active_layer_index < len(self.world.layers)):
            return

        layer = self.world.layers[self.active_layer_index]
        source_tiles = layer.tiles[:]
        ww, wh = self.world.world_w, self.world.world_h
        points = set()
        for x, y in changed:
            for oy in (-1, 0, 1):
                for ox in (-1, 0, 1):
                    nx, ny = x + ox, y + oy
                    if 0 <= nx < ww and 0 <= ny < wh:
                        points.add((nx, ny))

        updates: List[Tuple[int, int]] = []
        for x, y in points:
            pos = y * ww + x
            decoded = TileCodec.decode(source_tiles[pos])
            if decoded is None:
                continue
            tileset_index, tile_index = decoded
            if tileset_index < 0:
                continue
            group_start = (tile_index // AUTO_GROUP_SIZE) * AUTO_GROUP_SIZE
            group_end = group_start + AUTO_GROUP_SIZE
            tileset = self.tilesets[tileset_index] if 0 <= tileset_index < len(self.tilesets) else None
            if tileset is None or not tileset.valid or group_end > tileset.tile_count:
                continue

            mask = 0
            neighbors = [
                (0, -1, 1),
                (1, 0, 2),
                (0, 1, 4),
                (-1, 0, 8),
            ]
            for dx, dy, bit in neighbors:
                nx, ny = x + dx, y + dy
                if not (0 <= nx < ww and 0 <= ny < wh):
                    continue
                n_decoded = TileCodec.decode(source_tiles[ny * ww + nx])
                if n_decoded is None:
                    continue
                n_tileset_index, n_tile_index = n_decoded
                if n_tileset_index == tileset_index and (n_tile_index // AUTO_GROUP_SIZE) == (tile_index // AUTO_GROUP_SIZE):
                    mask |= bit
            new_index = group_start + mask
            if new_index < tileset.tile_count:
                updates.append((pos, TileCodec.encode(tileset_index, new_index)))

        for pos, value in updates:
            layer.tiles[pos] = value

    def wheelEvent(self, event) -> None:  # noqa: N802
        if event.modifiers() & Qt.ControlModifier and self.world is not None:
            angle = event.angleDelta().y()
            if angle == 0:
                return
            factor = ZOOM_STEP if angle > 0 else 1.0 / ZOOM_STEP
            old_zoom = self.zoom
            new_zoom = max(MIN_ZOOM, min(MAX_ZOOM, old_zoom * factor))
            if new_zoom == old_zoom:
                return
            pos = event.position()
            wx = (pos.x() - self.offset.x()) / old_zoom
            wy = (pos.y() - self.offset.y()) / old_zoom
            self.zoom = new_zoom
            self.offset = QPointF(pos.x() - wx * new_zoom, pos.y() - wy * new_zoom)
            self.zoomChanged.emit(self.zoom)
            self.update()
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.setFocus()
        if event.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_last_pos = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.LeftButton and self.world is not None:
            tile = self.screen_to_tile(event.position())
            if tile is not None:
                self.push_undo_state()
                tx, ty = tile
                self._painting = True
                self._last_stamp_origin = None
                if self.current_tool == ToolType.PENCIL:
                    self._paint_at(tx, ty)
                    self._last_stamp_origin = (tx, ty)
                elif self.current_tool == ToolType.BUCKET:
                    self._flood_fill(tx, ty)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._panning:
            pos = event.position().toPoint()
            delta = pos - self._pan_last_pos
            self.offset += QPointF(delta)
            self._pan_last_pos = pos
            self.update()
            event.accept()
            return

        tile = self.screen_to_tile(event.position())
        if tile != self._hover_tile:
            old_hover = self._hover_tile
            self._hover_tile = tile
            if old_hover is not None:
                self._update_tile_rect(*old_hover)
            if tile is not None:
                self._update_tile_rect(*tile)
            self.mouseTileChanged.emit(tile)

        if self._painting and tile is not None and self.current_tool == ToolType.PENCIL:
            if tile != self._last_stamp_origin:
                self._paint_at(*tile)
                self._last_stamp_origin = tile

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MiddleButton:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            self._painting = False
            self._last_stamp_origin = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hover_tile is not None:
            old = self._hover_tile
            self._hover_tile = None
            self._update_tile_rect(*old)
            self.mouseTileChanged.emit(None)
        super().leaveEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        if self.world is not None and not self._centered_once:
            self._centered_once = True
            self.center_view()
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        self._draw_checkerboard(painter)

        if self.world is None:
            painter.end()
            return

        tw = self.world.tile_w * self.zoom
        th = self.world.tile_h * self.zoom
        if tw <= 0 or th <= 0:
            painter.end()
            return

        w = self.width()
        h = self.height()
        start_tx = max(0, int((0 - self.offset.x()) / tw) - 1)
        start_ty = max(0, int((0 - self.offset.y()) / th) - 1)
        end_tx = min(self.world.world_w, int((w - self.offset.x()) / tw) + 2)
        end_ty = min(self.world.world_h, int((h - self.offset.y()) / th) + 2)

        painter.setRenderHint(QPainter.SmoothPixmapTransform, self.zoom < 1.0)

        for layer in self.world.layers:
            if not layer.visible:
                continue
            for ty in range(start_ty, end_ty):
                row_base = ty * self.world.world_w
                sy = self.offset.y() + ty * th
                for tx in range(start_tx, end_tx):
                    idx = layer.tiles[row_base + tx]
                    sx = self.offset.x() + tx * tw
                    rect = QRectF(sx, sy, tw + 0.5, th + 0.5)
                    self._draw_tile(painter, idx, rect)

        if self.show_grid and tw >= 3:
            painter.setPen(QPen(GRID_COLOR, 1))
            for tx in range(start_tx, end_tx + 1):
                x = self.offset.x() + tx * tw
                painter.drawLine(QPointF(x, self.offset.y() + start_ty * th), QPointF(x, self.offset.y() + end_ty * th))
            for ty in range(start_ty, end_ty + 1):
                y = self.offset.y() + ty * th
                painter.drawLine(QPointF(self.offset.x() + start_tx * tw, y), QPointF(self.offset.x() + end_tx * tw, y))

        if self._hover_tile is not None:
            hx, hy = self._hover_tile
            if 0 <= hx < self.world.world_w and 0 <= hy < self.world.world_h:
                rect = self.tile_screen_rect(hx, hy)
                painter.fillRect(rect, HOVER_COLOR)
                painter.setPen(QPen(SELECTED_BORDER, 2))
                painter.drawRect(rect.adjusted(1, 1, -1, -1))

        if self.current_stamp and self._hover_tile is not None:
            stamp_h = len(self.current_stamp)
            stamp_w = len(self.current_stamp[0]) if stamp_h else 0
            hx, hy = self._hover_tile
            preview = QRectF(
                self.offset.x() + hx * tw,
                self.offset.y() + hy * th,
                stamp_w * tw,
                stamp_h * th,
            )
            painter.setPen(QPen(QColor(255, 255, 255, 120), 1, Qt.DashLine))
            painter.drawRect(preview.adjusted(0.5, 0.5, -0.5, -0.5))

        map_rect = QRectF(self.offset.x(), self.offset.y(), self.world.world_w * tw, self.world.world_h * th)
        painter.setPen(QPen(QColor(20, 20, 24), 2))
        painter.drawRect(map_rect)
        painter.end()


class UnifiedMapView(MapView):
    """MapView with object-editor support layered on top."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.editor_mode: str = "tiles"  # "tiles" or "objects"
        self.object_tool: str = "select"  # select, trigger, wall, platform, spawn, enemy
        self.selected_object_index: Optional[int] = None
        self._obj_drag_mode: Optional[str] = None  # move, resize, create
        self._obj_drag_index: Optional[int] = None
        self._obj_drag_corner: Optional[int] = None
        self._obj_drag_start_world: Optional[Tuple[int, int]] = None
        self._obj_drag_offset: Tuple[int, int] = (0, 0)
        self._obj_create_index: Optional[int] = None
        self._obj_create_start: Optional[Tuple[int, int]] = None
        self._obj_create_kind: Optional[str] = None

    def set_world(self, world: Optional[World]) -> None:
        super().set_world(world)
        self.selected_object_index = None
        self._obj_drag_mode = None
        self._obj_drag_index = None
        self._obj_drag_corner = None
        self._obj_drag_start_world = None
        self._obj_create_index = None
        self._obj_create_start = None
        self._obj_create_kind = None

    # ---------- object helpers

    def _objects(self) -> List[EditorObject]:
        if self.world is None:
            return []
        return self.world.objects

    def _obj_rect(self, obj: EditorObject) -> QRectF:
        if obj.is_point():
            return QRectF(obj.x, obj.y, 1, 1)
        return QRectF(obj.x, obj.y, max(8, obj.w), max(8, obj.h))

    def _obj_corners(self, obj: EditorObject) -> List[Tuple[int, int]]:
        r = self._obj_rect(obj)
        return [
            (int(r.left()), int(r.top())),
            (int(r.right()), int(r.top())),
            (int(r.left()), int(r.bottom())),
            (int(r.right()), int(r.bottom())),
        ]

    def _pick_object(self, wx: int, wy: int) -> Optional[int]:
        for idx in range(len(self._objects()) - 1, -1, -1):
            obj = self._objects()[idx]
            r = self._obj_rect(obj).adjusted(-6, -6, 6, 6)
            if r.contains(wx, wy):
                return idx
        return None

    def _corner_hit(self, obj: EditorObject, wx: int, wy: int) -> Optional[int]:
        if obj.is_point():
            return None
        tol = 6
        for i, (cx, cy) in enumerate(self._obj_corners(obj)):
            if abs(wx - cx) <= tol and abs(wy - cy) <= tol:
                return i
        return None

    def _new_object(self, kind: str, wx: int, wy: int) -> EditorObject:
        if kind == "trigger":
            return EditorObject(kind="trigger", x=wx, y=wy, w=6, h=4, name="")
        if kind == "wall":
            return EditorObject(kind="wall", x=wx, y=wy, w=6, h=4, name="")
        if kind == "platform":
            return EditorObject(kind="platform", x=wx, y=wy, w=8, h=2, name="")
        if kind == "spawn":
            return EditorObject(kind="spawn", x=wx, y=wy, name="", came_from=0)
        if kind == "enemy":
            return EditorObject(kind="enemy", x=wx, y=wy, name="enemy")
        return EditorObject(kind=kind, x=wx, y=wy, w=64, h=64, name="")

    def _resize_object(self, obj: EditorObject, corner: int, wx: int, wy: int) -> None:
        x, y, w, h = obj.x, obj.y, max(8, obj.w), max(8, obj.h)
        brx, bry = x + w, y + h
        if corner == 0:
            obj.x, obj.y = wx, wy
            obj.w, obj.h = max(8, brx - wx), max(8, bry - wy)
        elif corner == 1:
            obj.y = wy
            obj.w, obj.h = max(8, wx - x), max(8, bry - wy)
        elif corner == 2:
            obj.x = wx
            obj.w, obj.h = max(8, brx - wx), max(8, wy - y)
        elif corner == 3:
            obj.w, obj.h = max(8, wx - x), max(8, wy - y)

    def _move_object(self, obj: EditorObject, wx: int, wy: int, offx: int, offy: int) -> None:
        nx, ny = (wx - offx), (wy - offy)
        if obj.is_point():
            obj.x, obj.y = int(nx), int(ny)
        else:
            obj.x, obj.y = int(nx), int(ny)

    def _selected_object(self) -> Optional[EditorObject]:
        if self.selected_object_index is None:
            return None
        objs = self._objects()
        if 0 <= self.selected_object_index < len(objs):
            return objs[self.selected_object_index]
        return None

    # ---------- render

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self.world is None:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        # Object overlays
        for idx, obj in enumerate(self._objects()):
            r = self._obj_rect(obj)
            screen = QRectF(
                self.offset.x() + r.x() * self.world.tile_w * self.zoom,
                self.offset.y() + r.y() * self.world.tile_h * self.zoom,
                r.width() * self.world.tile_w * self.zoom,
                r.height() * self.world.tile_h * self.zoom,
            )
            if obj.kind == "trigger":
                fill = QColor(200, 160, 48, 35)
                border = QColor(200, 160, 48)
            elif obj.kind == "wall":
                fill = QColor(48, 145, 200, 35)
                border = QColor(48, 145, 200)
            elif obj.kind == "platform":
                fill = QColor(55, 175, 100, 35)
                border = QColor(55, 175, 100)
            elif obj.kind == "spawn":
                fill = QColor(200, 80, 180, 35)
                border = QColor(200, 80, 180)
            else:
                fill = QColor(200, 80, 80, 35)
                border = QColor(200, 80, 80)

            if obj.is_point():
                cx = screen.center().x()
                cy = screen.center().y()
                painter.setBrush(QBrush(fill))
                painter.setPen(QPen(border, 2))
                painter.drawEllipse(QPointF(cx, cy), max(2, self.world.tile_w * self.zoom * 0.15), max(2, self.world.tile_h * self.zoom * 0.15))
                if obj.kind == "spawn":
                    painter.drawText(QPointF(cx + 10, cy + 4), str(obj.came_from))
                elif obj.kind == "enemy" and obj.name:
                    painter.drawText(QPointF(cx + 10, cy + 4), obj.name[:12])
            else:
                painter.setBrush(QBrush(fill))
                painter.setPen(QPen(border, 2))
                painter.drawRect(screen)
                if obj.kind == "trigger" and obj.name:
                    painter.drawText(screen.adjusted(4, 4, -4, -4), Qt.AlignLeft | Qt.AlignTop, obj.name[:12])

            if idx == self.selected_object_index:
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(OBJECT_SELECT, 2))
                painter.drawRect(screen.adjusted(1, 1, -1, -1))
                if not obj.is_point():
                    painter.setPen(QPen(OBJECT_SELECT, 2))
                    for cx, cy in self._obj_corners(obj):
                        sx = self.offset.x() + cx * self.world.tile_w * self.zoom
                        sy = self.offset.y() + cy * self.world.tile_h * self.zoom
                        painter.drawRect(QRectF(sx - 4, sy - 4, 8, 8))

        # In object mode, show a ghost preview for create/drag
        if self.editor_mode == "objects" and self._obj_drag_mode == "create" and self._obj_create_start and self._obj_create_index is not None:
            obj = self._objects()[self._obj_create_index]
            r = self._obj_rect(obj)
            screen = QRectF(
                self.offset.x() + r.x() * self.world.tile_w * self.zoom,
                self.offset.y() + r.y() * self.world.tile_h * self.zoom,
                r.width() * self.world.tile_w * self.zoom,
                r.height() * self.world.tile_h * self.zoom,
            )
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(255, 255, 255, 140), 1, Qt.DashLine))
            painter.drawRect(screen)
        painter.end()

    # ---------- interaction

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self.editor_mode != "objects":
            super().mousePressEvent(event)
            return

        self.setFocus()
        if event.button() == Qt.MiddleButton:
            super().mousePressEvent(event)
            return

        if event.button() != Qt.LeftButton or self.world is None:
            super().mousePressEvent(event)
            return

        tile = self.screen_to_tile(event.position())
        if tile is None:
            self.selected_object_index = None
            self.update()
            return

        wx, wy = tile
        self.push_undo_state()

        if self.object_tool == "select":
            hit = self._pick_object(wx, wy)
            self.selected_object_index = hit
            if hit is None:
                self.update()
                return
            obj = self._objects()[hit]
            corner = self._corner_hit(obj, wx, wy)
            if corner is not None:
                self._obj_drag_mode = "resize"
                self._obj_drag_index = hit
                self._obj_drag_corner = corner
            else:
                self._obj_drag_mode = "move"
                self._obj_drag_index = hit
                self._obj_drag_offset = (wx - obj.x, wy - obj.y)
            self.update()
            event.accept()
            return

        kind = self.object_tool
        new_obj = self._new_object(kind, wx, wy)
        self._objects().append(new_obj)
        self.selected_object_index = len(self._objects()) - 1

        if new_obj.is_point():
            self._obj_drag_mode = None
            self._obj_create_index = None
            self._obj_create_start = None
            self.activeLayerModified.emit()
            self.update()
            event.accept()
            return

        self._obj_drag_mode = "create"
        self._obj_create_index = self.selected_object_index
        self._obj_create_start = (wx, wy)
        self._obj_create_kind = kind
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self.editor_mode != "objects":
            super().mouseMoveEvent(event)
            return

        if self._panning:
            super().mouseMoveEvent(event)
            return

        tile = self.screen_to_tile(event.position())
        if tile != self._hover_tile:
            old_hover = self._hover_tile
            self._hover_tile = tile
            if old_hover is not None:
                self._update_tile_rect(*old_hover)
            if tile is not None:
                self._update_tile_rect(*tile)
            self.mouseTileChanged.emit(tile)

        if self.world is None or tile is None:
            super().mouseMoveEvent(event)
            return

        wx, wy = tile
        if self._obj_drag_mode == "move" and self._obj_drag_index is not None:
            obj = self._objects()[self._obj_drag_index]
            self._move_object(obj, wx, wy, *self._obj_drag_offset)
            self.activeLayerModified.emit()
            self.update()
            return

        if self._obj_drag_mode == "resize" and self._obj_drag_index is not None and self._obj_drag_corner is not None:
            obj = self._objects()[self._obj_drag_index]
            self._resize_object(obj, self._obj_drag_corner, wx, wy)
            self.activeLayerModified.emit()
            self.update()
            return

        if self._obj_drag_mode == "create" and self._obj_create_index is not None and self._obj_create_start is not None:
            obj = self._objects()[self._obj_create_index]
            sx, sy = self._obj_create_start
            obj.x = min(sx, wx)
            obj.y = min(sy, wy)
            obj.w = max(8, abs(wx - sx))
            obj.h = max(8, abs(wy - sy))
            self.activeLayerModified.emit()
            self.update()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self.editor_mode != "objects":
            super().mouseReleaseEvent(event)
            return

        if event.button() == Qt.LeftButton:
            self._obj_drag_mode = None
            self._obj_drag_index = None
            self._obj_drag_corner = None
            self._obj_drag_start_world = None
            self._obj_create_index = None
            self._obj_create_start = None
            self._obj_create_kind = None
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self.editor_mode == "objects":
            if event.key() == Qt.Key_Delete:
                if self.selected_object_index is not None and self.world is not None:
                    objs = self._objects()
                    if 0 <= self.selected_object_index < len(objs):
                        del objs[self.selected_object_index]
                        self.selected_object_index = None
                        self.activeLayerModified.emit()
                        self.update()
                        return
            if event.key() == Qt.Key_F2:
                obj = self._selected_object()
                if obj is not None:
                    text, ok = QInputDialog.getText(self, "Rename Object", "Name / label:", QLineEdit.Normal, obj.name)
                    if ok:
                        obj.name = text.strip()
                        self.activeLayerModified.emit()
                        self.update()
                        return
        super().keyPressEvent(event)


class TilesetPickerWidget(QWidget):
    selectionChanged = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.tileset: Optional[Tileset] = None
        self.zoom: float = 2.0
        self.selected_rect = QRect(0, 0, 1, 1)
        self._dragging = False
        self._drag_origin: Optional[QPoint] = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)

    def set_tileset(self, tileset: Optional[Tileset]) -> None:
        self.tileset = tileset
        self.selected_rect = QRect(0, 0, 1, 1)
        self._update_size()
        self.update()

    def set_selection(self, rect: QRect) -> None:
        self.selected_rect = QRect(rect)
        self.update()

    def _update_size(self) -> None:
        if self.tileset is not None and self.tileset.valid:
            w = int(self.tileset.pixmap.width() * self.zoom)
            h = int(self.tileset.pixmap.height() * self.zoom)
            self.setMinimumSize(QSize(max(w, 1), max(h, 1)))
        else:
            self.setMinimumSize(QSize(1, 1))
        self.resize(self.minimumSize())

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def _point_to_tile(self, pt: QPointF) -> Optional[QPoint]:
        if self.tileset is None or not self.tileset.valid:
            return None
        tw = self.tileset.tile_w * self.zoom
        th = self.tileset.tile_h * self.zoom
        if tw <= 0 or th <= 0:
            return None
        col = int(pt.x() / tw)
        row = int(pt.y() / th)
        if 0 <= col < self.tileset.columns and 0 <= row < self.tileset.rows:
            return QPoint(col, row)
        return None

    def _normalize_rect(self, a: QPoint, b: QPoint) -> QRect:
        left = min(a.x(), b.x())
        right = max(a.x(), b.x())
        top = min(a.y(), b.y())
        bottom = max(a.y(), b.y())
        return QRect(left, top, right - left + 1, bottom - top + 1)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), CHECKER_DARK)

        if self.tileset is None or not self.tileset.valid:
            painter.setPen(QColor(160, 160, 170))
            painter.drawText(self.rect(), Qt.AlignCenter, "No tileset loaded")
            painter.end()
            return

        tw = self.tileset.tile_w * self.zoom
        th = self.tileset.tile_h * self.zoom
        painter.drawPixmap(
            QRectF(0, 0, self.tileset.pixmap.width() * self.zoom, self.tileset.pixmap.height() * self.zoom),
            self.tileset.pixmap,
            QRectF(self.tileset.pixmap.rect()),
        )

        painter.setPen(QPen(GRID_COLOR, 1))
        for col in range(self.tileset.columns + 1):
            x = col * tw
            painter.drawLine(QPointF(x, 0), QPointF(x, self.tileset.rows * th))
        for row in range(self.tileset.rows + 1):
            y = row * th
            painter.drawLine(QPointF(0, y), QPointF(self.tileset.columns * tw, y))

        painter.setPen(QPen(SELECTED_BORDER, 3))
        painter.drawRect(QRectF(
            self.selected_rect.x() * tw,
            self.selected_rect.y() * th,
            self.selected_rect.width() * tw,
            self.selected_rect.height() * th,
        ).adjusted(1, 1, -1, -1))

        show_labels = th >= 16
        font = QFont(painter.font())
        font.setPointSize(max(6, min(9, int(th / 4))))
        painter.setFont(font)
        if show_labels:
            for index in range(self.tileset.tile_count):
                col = index % self.tileset.columns
                row = index // self.tileset.columns
                rect = QRectF(col * tw, row * th, tw, th)
                painter.setPen(QColor(255, 255, 255))
                text_rect = QRectF(rect.x() + 2, rect.y() + 1, rect.width() - 2, rect.height() - 2)
                painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignTop, str(index))
        painter.end()

    def wheelEvent(self, event) -> None:  # noqa: N802
        if event.modifiers() & Qt.ControlModifier and self.tileset is not None:
            angle = event.angleDelta().y()
            factor = ZOOM_STEP if angle > 0 else 1.0 / ZOOM_STEP
            self.zoom = max(0.5, min(16.0, self.zoom * factor))
            self._update_size()
            self.update()
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self.tileset is None or not self.tileset.valid:
            return
        if event.button() == Qt.LeftButton:
            tile = self._point_to_tile(event.position())
            if tile is not None:
                self._dragging = True
                self._drag_origin = tile
                rect = QRect(tile.x(), tile.y(), 1, 1)
                self.selected_rect = rect
                self.selectionChanged.emit(rect)
                self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragging and self._drag_origin is not None:
            tile = self._point_to_tile(event.position())
            if tile is not None:
                rect = self._normalize_rect(self._drag_origin, tile)
                if rect != self.selected_rect:
                    self.selected_rect = rect
                    self.selectionChanged.emit(rect)
                    self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self._drag_origin = None
            event.accept()
            return
        super().mouseReleaseEvent(event)


class LayerPanel(QWidget):
    activeLayerChanged = Signal(int)
    layersStructureChanged = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.world: Optional[World] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        title = QLabel("Layers")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.currentRowChanged.connect(self._on_row_changed)
        self.list_widget.itemChanged.connect(self._on_item_changed)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.list_widget, 1)

        btn_row1 = QHBoxLayout()
        self.add_btn = QPushButton("Add")
        self.remove_btn = QPushButton("Remove")
        self.rename_btn = QPushButton("Rename")
        btn_row1.addWidget(self.add_btn)
        btn_row1.addWidget(self.remove_btn)
        btn_row1.addWidget(self.rename_btn)
        layout.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()
        self.up_btn = QPushButton("Move Up")
        self.down_btn = QPushButton("Move Down")
        btn_row2.addWidget(self.up_btn)
        btn_row2.addWidget(self.down_btn)
        layout.addLayout(btn_row2)

        self.add_btn.clicked.connect(self._add_layer)
        self.remove_btn.clicked.connect(self._remove_layer)
        self.rename_btn.clicked.connect(self._rename_selected)
        self.up_btn.clicked.connect(self._move_up)
        self.down_btn.clicked.connect(self._move_down)

        self._suppress_signals = False

    def _ui_to_array(self, ui_row: int) -> int:
        return len(self.world.layers) - 1 - ui_row

    def _array_to_ui(self, array_index: int) -> int:
        return len(self.world.layers) - 1 - array_index

    def set_world(self, world: Optional[World]) -> None:
        self.world = world
        self.refresh()

    def refresh(self, select_array_index: Optional[int] = None) -> None:
        self._suppress_signals = True
        self.list_widget.clear()
        if self.world is not None:
            for array_index in reversed(range(len(self.world.layers))):
                layer = self.world.layers[array_index]
                item = QListWidgetItem(layer.name)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if layer.visible else Qt.Unchecked)
                self.list_widget.addItem(item)
        self._suppress_signals = False

        if self.world is not None and self.world.layers:
            if select_array_index is None:
                select_array_index = 0
            select_array_index = max(0, min(select_array_index, len(self.world.layers) - 1))
            self.list_widget.setCurrentRow(self._array_to_ui(select_array_index))

    def current_array_index(self) -> int:
        row = self.list_widget.currentRow()
        if row < 0 or self.world is None:
            return 0
        return self._ui_to_array(row)

    def _on_row_changed(self, ui_row: int) -> None:
        if self._suppress_signals or self.world is None or ui_row < 0:
            return
        self.activeLayerChanged.emit(self._ui_to_array(ui_row))

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._suppress_signals or self.world is None:
            return
        ui_row = self.list_widget.row(item)
        if ui_row < 0:
            return
        array_index = self._ui_to_array(ui_row)
        self.world.layers[array_index].visible = item.checkState() == Qt.Checked
        self.world.layers[array_index].name = item.text()
        self.layersStructureChanged.emit()

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        self._rename_selected()

    def _add_layer(self) -> None:
        if self.world is None:
            return
        new_layer = Layer(name=f"Layer {len(self.world.layers) + 1}", tiles=[MISSING_TILE] * self.world.tile_count())
        self.world.layers.append(new_layer)
        self.refresh(select_array_index=len(self.world.layers) - 1)
        self.layersStructureChanged.emit()

    def _remove_layer(self) -> None:
        if self.world is None or not self.world.layers:
            return
        if len(self.world.layers) <= 1:
            QMessageBox.warning(self, "Cannot Remove Layer", "A world must have at least one layer.")
            return
        array_index = self.current_array_index()
        del self.world.layers[array_index]
        new_select = max(0, array_index - 1)
        self.refresh(select_array_index=new_select)
        self.layersStructureChanged.emit()

    def _rename_selected(self) -> None:
        if self.world is None or not self.world.layers:
            return
        from PySide6.QtWidgets import QInputDialog

        array_index = self.current_array_index()
        current_name = self.world.layers[array_index].name
        new_name, ok = QInputDialog.getText(self, "Rename Layer", "Layer name:", QLineEdit.Normal, current_name)
        if ok and new_name.strip():
            self.world.layers[array_index].name = new_name.strip()
            self.refresh(select_array_index=array_index)
            self.layersStructureChanged.emit()

    def _move_up(self) -> None:
        if self.world is None or len(self.world.layers) < 2:
            return
        array_index = self.current_array_index()
        if array_index >= len(self.world.layers) - 1:
            return
        self.world.layers[array_index], self.world.layers[array_index + 1] = (
            self.world.layers[array_index + 1],
            self.world.layers[array_index],
        )
        self.refresh(select_array_index=array_index + 1)
        self.layersStructureChanged.emit()

    def _move_down(self) -> None:
        if self.world is None or len(self.world.layers) < 2:
            return
        array_index = self.current_array_index()
        if array_index <= 0:
            return
        self.world.layers[array_index], self.world.layers[array_index - 1] = (
            self.world.layers[array_index - 1],
            self.world.layers[array_index],
        )
        self.refresh(select_array_index=array_index - 1)
        self.layersStructureChanged.emit()


@dataclass
class NewWorldParams:
    world_w: int
    world_h: int
    tile_w: int
    tile_h: int
    layer_count: int
    tileset_filenames: List[str]


class NewWorldDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("New World")
        self.setMinimumWidth(420)

        form = QFormLayout()

        self.world_w_spin = QSpinBox()
        self.world_w_spin.setRange(1, 100000)
        self.world_w_spin.setValue(25)

        self.world_h_spin = QSpinBox()
        self.world_h_spin.setRange(1, 100000)
        self.world_h_spin.setValue(50)

        self.tile_w_spin = QSpinBox()
        self.tile_w_spin.setRange(1, 4096)
        self.tile_w_spin.setValue(8)

        self.tile_h_spin = QSpinBox()
        self.tile_h_spin.setRange(1, 4096)
        self.tile_h_spin.setValue(8)

        self.layer_count_spin = QSpinBox()
        self.layer_count_spin.setRange(1, 256)
        self.layer_count_spin.setValue(1)

        tileset_row = QHBoxLayout()
        self.tileset_edit = QLineEdit("overworld.png")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse)
        tileset_row.addWidget(self.tileset_edit)
        tileset_row.addWidget(browse_btn)
        tileset_container = QWidget()
        tileset_container.setLayout(tileset_row)

        form.addRow("World Width (tiles):", self.world_w_spin)
        form.addRow("World Height (tiles):", self.world_h_spin)
        form.addRow("Tile Width (px):", self.tile_w_spin)
        form.addRow("Tile Height (px):", self.tile_h_spin)
        form.addRow("Layer Count:", self.layer_count_spin)
        form.addRow("Tileset Filenames (comma-separated):", tileset_container)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        main_layout = QVBoxLayout(self)
        main_layout.addLayout(form)
        main_layout.addWidget(buttons)

    def _browse(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Select Tileset Images", "", "PNG Images (*.png);;All Files (*)")
        if paths:
            self.tileset_edit.setText(", ".join(os.path.basename(p) for p in paths))

    def get_params(self) -> NewWorldParams:
        raw = self.tileset_edit.text().strip()
        tileset_filenames = [part.strip() for part in raw.split(",") if part.strip()]
        if not tileset_filenames:
            tileset_filenames = ["overworld.png"]
        return NewWorldParams(
            world_w=self.world_w_spin.value(),
            world_h=self.world_h_spin.value(),
            tile_w=self.tile_w_spin.value(),
            tile_h=self.tile_h_spin.value(),
            layer_count=self.layer_count_spin.value(),
            tileset_filenames=tileset_filenames,
        )


DARK_STYLESHEET = """
QMainWindow {
    background-color: #1e1e22;
}
QWidget {
    color: #e6e6ea;
    font-family: "Segoe UI", "Cantarell", "Helvetica Neue", sans-serif;
    font-size: 12px;
}
QLabel#panelTitle {
    font-weight: 600;
    font-size: 13px;
    color: #9fb8ff;
    padding: 2px 0px 4px 0px;
}
QMenuBar {
    background-color: #232327;
    border-bottom: 1px solid #33333a;
}
QMenuBar::item {
    padding: 6px 12px;
    background: transparent;
}
QMenuBar::item:selected {
    background-color: #33445f;
    border-radius: 4px;
}
QMenu {
    background-color: #26262b;
    border: 1px solid #38383f;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #3a5a99;
}
QToolBar {
    background-color: #232327;
    border-bottom: 1px solid #33333a;
    padding: 4px;
    spacing: 4px;
}
QToolBar QToolButton {
    background-color: #2b2b31;
    border: 1px solid #3a3a42;
    border-radius: 6px;
    padding: 6px;
}
QToolBar QToolButton:hover {
    background-color: #34445f;
    border-color: #4a6fa5;
}
QToolBar QToolButton:checked {
    background-color: #3a5a99;
    border-color: #5f8fe0;
}
QStatusBar {
    background-color: #232327;
    border-top: 1px solid #33333a;
}
QPushButton {
    background-color: #2b2b31;
    border: 1px solid #3a3a42;
    border-radius: 8px;
    padding: 6px 14px;
}
QPushButton:hover {
    background-color: #34445f;
    border-color: #4a6fa5;
}
QPushButton:pressed {
    background-color: #26344a;
}
QListWidget {
    background-color: #202024;
    border: 1px solid #33333a;
    border-radius: 6px;
    padding: 4px;
}
QListWidget::item {
    padding: 6px;
    border-radius: 4px;
}
QListWidget::item:selected {
    background-color: #3a5a99;
}
QScrollArea {
    background-color: #1a1a1e;
    border: 1px solid #33333a;
    border-radius: 6px;
}
QSpinBox, QLineEdit, QComboBox {
    background-color: #232327;
    border: 1px solid #3a3a42;
    border-radius: 6px;
    padding: 4px 6px;
}
QSplitter::handle {
    background-color: #2b2b31;
}
QSplitter::handle:horizontal {
    width: 4px;
}
QSplitter::handle:vertical {
    height: 4px;
}
QDialog {
    background-color: #232327;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background: #1e1e22;
    border: none;
    width: 12px;
    height: 12px;
}
QScrollBar::handle {
    background: #45454f;
    border-radius: 5px;
    min-height: 20px;
    min-width: 20px;
}
QScrollBar::handle:hover {
    background: #5a5a68;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0px;
    height: 0px;
}
"""


def apply_dark_palette(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(30, 30, 34))
    palette.setColor(QPalette.WindowText, QColor(230, 230, 234))
    palette.setColor(QPalette.Base, QColor(32, 32, 36))
    palette.setColor(QPalette.AlternateBase, QColor(40, 40, 46))
    palette.setColor(QPalette.ToolTipBase, QColor(40, 40, 46))
    palette.setColor(QPalette.ToolTipText, QColor(230, 230, 234))
    palette.setColor(QPalette.Text, QColor(230, 230, 234))
    palette.setColor(QPalette.Button, QColor(43, 43, 49))
    palette.setColor(QPalette.ButtonText, QColor(230, 230, 234))
    palette.setColor(QPalette.BrightText, QColor(255, 80, 80))
    palette.setColor(QPalette.Highlight, QColor(58, 90, 153))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)
    app.setStyleSheet(DARK_STYLESHEET)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("i think i think too much")
        self.resize(1400, 900)

        self.world: Optional[World] = None
        self.current_file_path: Optional[str] = None
        self.tilesets: List[Optional[Tileset]] = []
        self.tileset_selections: Dict[int, QRect] = {}
        self.active_tileset_index: int = 0

        self._build_central_widgets()
        self._build_toolbar()
        self._build_menu()
        self._build_status_bar()
        self._wire_signals()

        self._new_blank_world(25, 50, 8, 8, 1, ["overworld.png"], tileset_paths=None)

    def _build_central_widgets(self) -> None:
        self.map_view = UnifiedMapView()
        self.tileset_picker = TilesetPickerWidget()
        self.layer_panel = LayerPanel()

        tileset_controls = QWidget()
        controls_layout = QHBoxLayout(tileset_controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)
        self.tileset_combo = QComboBox()
        self.tileset_combo.currentIndexChanged.connect(self._on_tileset_changed)
        self.load_tileset_btn = QPushButton("Add Tileset...")
        self.load_tileset_btn.clicked.connect(self.on_open_tileset)
        controls_layout.addWidget(QLabel("Tilesets:"))
        controls_layout.addWidget(self.tileset_combo, 1)
        controls_layout.addWidget(self.load_tileset_btn)

        tileset_scroll = QScrollArea()
        tileset_scroll.setWidget(self.tileset_picker)
        tileset_scroll.setWidgetResizable(False)
        tileset_scroll.setMinimumHeight(160)
        tileset_scroll.setMaximumHeight(320)

        tileset_container = QWidget()
        tileset_layout = QVBoxLayout(tileset_container)
        tileset_layout.setContentsMargins(6, 6, 6, 6)
        tileset_layout.setSpacing(4)
        tileset_title = QLabel("Tile Picker")
        tileset_title.setObjectName("panelTitle")
        tileset_layout.addWidget(tileset_title)
        tileset_layout.addWidget(tileset_controls)
        tileset_layout.addWidget(tileset_scroll)

        left_splitter = QSplitter(Qt.Vertical)
        left_splitter.addWidget(self.map_view)
        left_splitter.addWidget(tileset_container)
        left_splitter.setStretchFactor(0, 4)
        left_splitter.setStretchFactor(1, 1)

        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.addWidget(left_splitter)
        main_splitter.addWidget(self.layer_panel)
        main_splitter.setStretchFactor(0, 4)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setSizes([1050, 250])
        self.setCentralWidget(main_splitter)

    def _make_tool_icon(self, kind: str) -> QIcon:
        size = 24
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(QColor(220, 220, 230), 2)
        painter.setPen(pen)

        if kind == "pencil":
            painter.setBrush(QBrush(QColor(220, 180, 90)))
            painter.drawPolygon([QPoint(4, 20), QPoint(16, 4), QPoint(20, 8), QPoint(8, 20)])
            painter.drawLine(4, 20, 8, 20)
        elif kind == "bucket":
            painter.setBrush(QBrush(QColor(90, 160, 220)))
            painter.drawRect(4, 10, 14, 10)
            painter.drawLine(11, 2, 11, 10)
            painter.drawEllipse(QPoint(11, 10), 4, 3)
        elif kind == "grid":
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(3, 3, 18, 18)
            painter.drawLine(3, 11, 21, 11)
            painter.drawLine(11, 3, 11, 21)
        elif kind == "center":
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPoint(12, 12), 8, 8)
            painter.drawEllipse(QPoint(12, 12), 2, 2)
        elif kind == "tiles":
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(4, 4, 16, 16)
            painter.drawLine(12, 4, 12, 20)
            painter.drawLine(4, 12, 20, 12)
        elif kind == "objects":
            painter.setBrush(QBrush(QColor(120, 200, 255)))
            painter.drawRoundedRect(4, 6, 16, 12, 3, 3)
            painter.drawEllipse(QPoint(8, 12), 2, 2)
            painter.drawEllipse(QPoint(16, 12), 2, 2)
        elif kind == "auto":
            painter.setBrush(QBrush(QColor(180, 120, 220)))
            painter.drawRoundedRect(4, 4, 16, 16, 4, 4)
            painter.drawText(7, 16, "A")
        elif kind == "undo":
            painter.setBrush(Qt.NoBrush)
            painter.drawArc(4, 4, 16, 16, 45 * 16, 270 * 16)
            painter.drawLine(7, 7, 4, 10)
            painter.drawLine(7, 7, 10, 4)
        painter.end()
        return QIcon(pixmap)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Tools")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)

        self.pencil_action = QAction("Pencil", self)
        self.pencil_action.setCheckable(True)
        self.pencil_action.setChecked(True)
        self.pencil_action.setShortcut(QKeySequence("P"))
        self.pencil_action.setIcon(self._make_tool_icon("pencil"))

        self.bucket_action = QAction("Bucket Fill", self)
        self.bucket_action.setCheckable(True)
        self.bucket_action.setShortcut(QKeySequence("B"))
        self.bucket_action.setIcon(self._make_tool_icon("bucket"))

        self.auto_tile_action = QAction("Auto-Tile", self)
        self.auto_tile_action.setCheckable(True)
        self.auto_tile_action.setShortcut(QKeySequence("A"))
        self.auto_tile_action.setIcon(self._make_tool_icon("auto"))

        self.tool_group.addAction(self.pencil_action)
        self.tool_group.addAction(self.bucket_action)

        toolbar.addAction(self.pencil_action)
        toolbar.addAction(self.bucket_action)
        toolbar.addAction(self.auto_tile_action)
        toolbar.addSeparator()

        self.mode_group = QActionGroup(self)
        self.mode_group.setExclusive(True)
        self.tiles_mode_action = QAction("Tiles", self)
        self.tiles_mode_action.setCheckable(True)
        self.tiles_mode_action.setChecked(True)
        self.tiles_mode_action.setIcon(self._make_tool_icon("tiles"))
        self.objects_mode_action = QAction("Objects", self)
        self.objects_mode_action.setCheckable(True)
        self.objects_mode_action.setIcon(self._make_tool_icon("objects"))
        self.mode_group.addAction(self.tiles_mode_action)
        self.mode_group.addAction(self.objects_mode_action)
        toolbar.addAction(self.tiles_mode_action)
        toolbar.addAction(self.objects_mode_action)
        toolbar.addSeparator()

        self.object_tool_group = QActionGroup(self)
        self.object_tool_group.setExclusive(True)
        self.object_select_action = QAction("Select", self)
        self.object_select_action.setCheckable(True)
        self.object_select_action.setChecked(True)
        self.object_trigger_action = QAction("Trigger", self)
        self.object_trigger_action.setCheckable(True)
        self.object_wall_action = QAction("Wall", self)
        self.object_wall_action.setCheckable(True)
        self.object_platform_action = QAction("Platform", self)
        self.object_platform_action.setCheckable(True)
        self.object_spawn_action = QAction("Spawn", self)
        self.object_spawn_action.setCheckable(True)
        self.object_enemy_action = QAction("Enemy", self)
        self.object_enemy_action.setCheckable(True)
        for act in (self.object_select_action, self.object_trigger_action, self.object_wall_action, self.object_platform_action, self.object_spawn_action, self.object_enemy_action):
            self.object_tool_group.addAction(act)
        toolbar.addAction(self.object_select_action)
        toolbar.addAction(self.object_trigger_action)
        toolbar.addAction(self.object_wall_action)
        toolbar.addAction(self.object_platform_action)
        toolbar.addAction(self.object_spawn_action)
        toolbar.addAction(self.object_enemy_action)
        toolbar.addSeparator()

        self.grid_action = QAction("Grid", self)
        self.grid_action.setCheckable(True)
        self.grid_action.setChecked(True)
        self.grid_action.setIcon(self._make_tool_icon("grid"))
        toolbar.addAction(self.grid_action)

        toolbar.addSeparator()
        center_action = QAction("Center View", self)
        center_action.setIcon(self._make_tool_icon("center"))
        center_action.triggered.connect(self.map_view.center_view)
        toolbar.addAction(center_action)

        toolbar.addSeparator()
        self.toolbar_undo_action = QAction("Undo", self)
        self.toolbar_undo_action.setShortcut(QKeySequence.Undo)
        self.toolbar_undo_action.setIcon(self._make_tool_icon("undo"))
        self.toolbar_undo_action.triggered.connect(self.on_undo)
        toolbar.addAction(self.toolbar_undo_action)

        self.toolbar = toolbar

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")
        edit_menu = menu_bar.addMenu("&Edit")

        new_world_action = QAction("New World...", self)
        new_world_action.setShortcut(QKeySequence.New)
        new_world_action.triggered.connect(self.on_new_world)
        file_menu.addAction(new_world_action)

        open_world_action = QAction("Open .world...", self)
        open_world_action.setShortcut(QKeySequence.Open)
        open_world_action.triggered.connect(self.on_open_world)
        file_menu.addAction(open_world_action)

        file_menu.addSeparator()

        save_action = QAction("Save", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self.on_save)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save As...", self)
        save_as_action.setShortcut(QKeySequence.SaveAs)
        save_as_action.triggered.connect(self.on_save_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        open_tileset_action = QAction("Add Tileset PNG...", self)
        open_tileset_action.triggered.connect(self.on_open_tileset)
        file_menu.addAction(open_tileset_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.undo_action.triggered.connect(self.on_undo)
        edit_menu.addAction(self.undo_action)

    def _build_status_bar(self) -> None:
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        self.tool_label = QLabel("Tool: Pencil")
        self.tile_label = QLabel("Tile: 0")
        self.coord_label = QLabel("Position: -, -")
        self.zoom_label = QLabel("Zoom: 300%")
        self.layer_label = QLabel("Layer: Layer 1")
        self.tileset_label = QLabel("Tileset: 1")

        for lbl in (self.tool_label, self.tile_label, self.coord_label, self.zoom_label, self.layer_label, self.tileset_label):
            lbl.setContentsMargins(8, 0, 8, 0)
            status_bar.addWidget(lbl)

    def _wire_signals(self) -> None:
        self.pencil_action.triggered.connect(lambda: self._set_tool(ToolType.PENCIL))
        self.bucket_action.triggered.connect(lambda: self._set_tool(ToolType.BUCKET))
        self.grid_action.toggled.connect(self._set_grid_visible)
        self.auto_tile_action.toggled.connect(self.map_view.set_auto_tile_enabled)

        self.tiles_mode_action.triggered.connect(lambda: self._set_mode("tiles"))
        self.objects_mode_action.triggered.connect(lambda: self._set_mode("objects"))
        self.object_select_action.triggered.connect(lambda: self._set_object_tool("select"))
        self.object_trigger_action.triggered.connect(lambda: self._set_object_tool("trigger"))
        self.object_wall_action.triggered.connect(lambda: self._set_object_tool("wall"))
        self.object_platform_action.triggered.connect(lambda: self._set_object_tool("platform"))
        self.object_spawn_action.triggered.connect(lambda: self._set_object_tool("spawn"))
        self.object_enemy_action.triggered.connect(lambda: self._set_object_tool("enemy"))

        self.map_view.mouseTileChanged.connect(self._on_mouse_tile_changed)
        self.map_view.zoomChanged.connect(self._on_zoom_changed)
        self.map_view.activeLayerModified.connect(self._on_map_modified)
        self.tileset_picker.selectionChanged.connect(self._on_picker_selection_changed)

        self.layer_panel.activeLayerChanged.connect(self._on_active_layer_changed)
        self.layer_panel.layersStructureChanged.connect(self._on_layers_structure_changed)

    def _set_tool(self, tool: ToolType) -> None:
        self.map_view.current_tool = tool
        name = "Pencil" if tool == ToolType.PENCIL else "Bucket Fill"
        self.tool_label.setText(f"Tool: {name}")

    def _set_mode(self, mode: str) -> None:
        self.map_view.editor_mode = mode
        self.mode_label.setText(f"Mode: {'Objects' if mode == 'objects' else 'Tiles'}")
        self.map_view.update()

    def _set_object_tool(self, tool: str) -> None:
        self.map_view.object_tool = tool
        self._set_mode("objects")
        if hasattr(self, "object_label"):
            self.object_label.setText("Object: none")
        self.map_view.update()

    def _set_grid_visible(self, visible: bool) -> None:
        self.map_view.show_grid = visible
        self.map_view.update()

    def _on_mouse_tile_changed(self, tile: Optional[Tuple[int, int]]) -> None:
        if tile is None:
            self.coord_label.setText("Position: -, -")
        else:
            self.coord_label.setText(f"Position: {tile[0]}, {tile[1]}")

    def _on_zoom_changed(self, zoom: float) -> None:
        self.zoom_label.setText(f"Zoom: {int(round(zoom * 100))}%")

    def _on_map_modified(self) -> None:
        self.map_view.update()
        obj = self.map_view._selected_object() if hasattr(self.map_view, "_selected_object") else None
        if obj is None:
            if hasattr(self, "object_label"):
                self.object_label.setText("Object: none")
        else:
            label = obj.kind
            if obj.kind == "enemy" and obj.name:
                label += f" ({obj.name})"
            elif obj.kind == "spawn":
                label += f" ({obj.came_from})"
                if hasattr(self, "object_label"):
                    self.object_label.setText("Object: none")

    def _on_picker_selection_changed(self, rect_obj: object) -> None:
        if not isinstance(rect_obj, QRect):
            return
        self.tileset_selections[self.active_tileset_index] = QRect(rect_obj)
        self._rebuild_stamp_from_selection()

    def _rebuild_stamp_from_selection(self) -> None:
        if not self.tilesets:
            self.map_view.set_current_stamp([[MISSING_TILE]])
            self.tile_label.setText("Tile: -")
            return
        active = self.active_tileset_index
        tileset = self.tilesets[active] if 0 <= active < len(self.tilesets) else None
        if tileset is None or not tileset.valid:
            self.map_view.set_current_stamp([[MISSING_TILE]])
            self.tile_label.setText("Tile: -")
            return
        rect = self.tileset_selections.get(active, QRect(0, 0, 1, 1))
        rect = QRect(rect)
        rect.setX(max(0, min(rect.x(), max(0, tileset.columns - 1))))
        rect.setY(max(0, min(rect.y(), max(0, tileset.rows - 1))))
        rect.setWidth(max(1, min(rect.width(), tileset.columns - rect.x())))
        rect.setHeight(max(1, min(rect.height(), tileset.rows - rect.y())))
        stamp: List[List[int]] = []
        for row in range(rect.y(), rect.y() + rect.height()):
            line: List[int] = []
            for col in range(rect.x(), rect.x() + rect.width()):
                tile_index = row * tileset.columns + col
                line.append(TileCodec.encode(active, tile_index))
            stamp.append(line)
        self.map_view.set_current_stamp(stamp)
        if rect.width() == 1 and rect.height() == 1:
            self.tile_label.setText(f"Tile: {rect.x() + rect.y() * tileset.columns}")
        else:
            self.tile_label.setText(f"Tile: {rect.width()}x{rect.height()}")
        self.tileset_label.setText(f"Tileset: {active + 1}/{len(self.tilesets)}")

    def _on_tileset_changed(self, index: int) -> None:
        if index < 0 or index >= len(self.tilesets):
            return
        self.active_tileset_index = index
        tileset = self.tilesets[index]
        self.tileset_picker.set_tileset(tileset)
        if index in self.tileset_selections:
            self.tileset_picker.set_selection(self.tileset_selections[index])
        else:
            self.tileset_selections[index] = QRect(0, 0, 1, 1)
            self.tileset_picker.set_selection(self.tileset_selections[index])
        self._rebuild_stamp_from_selection()

    def _on_active_layer_changed(self, array_index: int) -> None:
        self.map_view.active_layer_index = array_index
        if self.world is not None and 0 <= array_index < len(self.world.layers):
            self.layer_label.setText(f"Layer: {self.world.layers[array_index].name}")
        self.map_view.update()

    def _on_layers_structure_changed(self) -> None:
        self.map_view.update()
        self._on_active_layer_changed(self.layer_panel.current_array_index())

    def _set_world(self, world: World, current_file_path: Optional[str] = None, tileset_paths: Optional[List[Optional[str]]] = None) -> None:
        self.world = world
        self.current_file_path = current_file_path

        if current_file_path:
            self._load_objects_for_world(current_file_path, world)
        else:
            world.objects = []

        self.tilesets = []
        base_dir = os.path.dirname(current_file_path) if current_file_path else os.getcwd()
        source_paths: List[Optional[str]] = []
        if tileset_paths is not None and len(tileset_paths) >= len(world.image_names):
            source_paths = list(tileset_paths)
        else:
            source_paths = [None] * len(world.image_names)

        if len(source_paths) < len(world.image_names):
            source_paths.extend([None] * (len(world.image_names) - len(source_paths)))

        for idx, name in enumerate(world.image_names):
            candidate = source_paths[idx]
            if not candidate:
                candidate = os.path.join(base_dir, name)
                if not os.path.isfile(candidate):
                    candidate = name
            pixmap = QPixmap(candidate) if candidate and os.path.isfile(candidate) else QPixmap()
            tileset = Tileset(pixmap if not pixmap.isNull() else None, world.tile_w, world.tile_h, source_path=candidate if candidate and os.path.isfile(candidate) else None)
            self.tilesets.append(tileset if tileset.valid else None)

        if not self.tilesets:
            self.tilesets = [None]
            world.image_names = [world.image_name or "overworld.png"]

        world.tileset_paths = [ts.source_path if ts is not None else None for ts in self.tilesets]

        self.map_view.set_world(world)
        self.map_view.set_tilesets(self.tilesets)
        self.layer_panel.set_world(world)

        self.tileset_combo.blockSignals(True)
        self.tileset_combo.clear()
        for idx, name in enumerate(world.image_names):
            self.tileset_combo.addItem(f"{idx + 1}: {name}")
        self.tileset_combo.blockSignals(False)

        self.active_tileset_index = 0
        if self.tilesets:
            self.tileset_combo.setCurrentIndex(0)
        self.tileset_picker.set_tileset(self.tilesets[0] if self.tilesets else None)
        self.tileset_selections.setdefault(0, QRect(0, 0, 1, 1))
        self.tileset_picker.set_selection(self.tileset_selections[0])
        self._rebuild_stamp_from_selection()
        self._on_active_layer_changed(0)
        self._on_map_modified()
        self.zoom_label.setText(f"Zoom: {int(round(self.map_view.zoom * 100))}%")
        self.setWindowTitle("i think i think too much" if not current_file_path else f"i think i think too much — {os.path.basename(current_file_path)}")

    def _new_blank_world(self, world_w: int, world_h: int, tile_w: int, tile_h: int, layer_count: int, tileset_filenames: List[str], tileset_paths: Optional[List[Optional[str]]]) -> None:
        tile_count = world_w * world_h
        layers = [Layer(name=f"Layer {i + 1}", tiles=[MISSING_TILE] * tile_count) for i in range(layer_count)]
        world = World(
            image_names=list(tileset_filenames),
            tile_w=tile_w,
            tile_h=tile_h,
            world_w=world_w,
            world_h=world_h,
            layers=layers,
            objects=[],
        )
        self._set_world(world, None, tileset_paths=tileset_paths)

    def on_new_world(self) -> None:
        dialog = NewWorldDialog(self)
        if dialog.exec() == QDialog.Accepted:
            params = dialog.get_params()
            self._new_blank_world(
                params.world_w,
                params.world_h,
                params.tile_w,
                params.tile_h,
                params.layer_count,
                params.tileset_filenames,
                tileset_paths=[None] * len(params.tileset_filenames),
            )

    def on_open_world(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open World", "", "World Files (*.world);;All Files (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            world = WorldParser.parse(text)
        except FileNotFoundError:
            QMessageBox.critical(self, "Error", f"File not found:\n{path}")
            return
        except WorldParseError as exc:
            QMessageBox.critical(self, "Corrupt World File", f"Failed to parse world file:\n{exc}")
            return
        except OSError as exc:
            QMessageBox.critical(self, "Error", f"Could not read file:\n{exc}")
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Unexpected Error", f"An unexpected error occurred:\n{exc}")
            return

        self._set_world(world, path)

    def _resolve_tileset_path(self, name: str, base_dir: str) -> str:
        if os.path.isabs(name) and os.path.isfile(name):
            return name
        candidate = os.path.join(base_dir, name)
        if os.path.isfile(candidate):
            return candidate
        return name

    def _objects_sidecar_path(self, world_path: str) -> str:
        p = Path(world_path)
        return str(p.with_suffix(".objects.json"))

    def _load_objects_for_world(self, world_path: Optional[str], world: World) -> None:
        world.objects = []
        if not world_path:
            return
        sidecar = self._objects_sidecar_path(world_path)
        if not os.path.isfile(sidecar):
            return
        try:
            with open(sidecar, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw_objects = data.get("objects", [])
            objs: List[EditorObject] = []
            for item in raw_objects:
                if not isinstance(item, dict):
                    continue
                kind = item.get("kind", "trigger")
                objs.append(EditorObject(
                    kind=kind,
                    x=int(item.get("x", 0)),
                    y=int(item.get("y", 0)),
                    w=int(item.get("w", 0)),
                    h=int(item.get("h", 0)),
                    name=str(item.get("name", "")),
                    came_from=int(item.get("came_from", 0)),
                    obj_id=str(item.get("obj_id", uuid.uuid4().hex)),
                ))
            world.objects = objs
            world.objects_path = sidecar
        except Exception:
            world.objects = []

    def _save_objects_for_world(self, world_path: str) -> None:
        if self.world is None:
            return
        sidecar = self._objects_sidecar_path(world_path)
        payload = {"objects": [asdict(obj) for obj in self.world.objects]}
        with open(sidecar, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        self.world.objects_path = sidecar

    def on_save(self) -> None:
        if self.world is None:
            return
        if self.current_file_path is None:
            self.on_save_as()
            return
        self._write_world(self.current_file_path)

    def on_save_as(self) -> None:
        if self.world is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save World", "", "World Files (*.world);;All Files (*)")
        if not path:
            return
        if not path.lower().endswith(".world"):
            path += ".world"
        self._write_world(path)

    def _write_world(self, path: str) -> None:
        try:
            text = WorldParser.serialize(self.world)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as exc:
            QMessageBox.critical(self, "Save Error", f"Could not save file:\n{exc}")
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Unexpected Error", f"An unexpected error occurred while saving:\n{exc}")
            return

        self.current_file_path = path
        self.world.source_path = path
        try:
            self._save_objects_for_world(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Object Save Warning", f"Saved tiles, but could not save objects:\n{exc}")
        self.setWindowTitle(f"i think i think too much — {os.path.basename(path)}")
        self.statusBar().showMessage(f"Saved to {path}", 4000)

    def on_open_tileset(self) -> None:
        if self.world is None:
            QMessageBox.warning(self, "No World Loaded", "Create or open a world first.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Tileset PNG", "", "PNG Images (*.png);;All Files (*)")
        if not path:
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            QMessageBox.critical(self, "Invalid Image", f"Could not load image as a valid PNG:\n{path}")
            return
        tileset = Tileset(pixmap, self.world.tile_w, self.world.tile_h, source_path=path)
        self.tilesets.append(tileset)
        self.world.image_names.append(os.path.basename(path))
        self.world.tileset_paths.append(path)
        self.tileset_combo.addItem(f"{self.tileset_combo.count() + 1}: {os.path.basename(path)}")
        self.tileset_combo.setCurrentIndex(len(self.tilesets) - 1)
        self.map_view.set_tilesets(self.tilesets)
        self.statusBar().showMessage(f"Loaded tileset: {os.path.basename(path)}", 4000)

    def on_undo(self) -> None:
        restored = self.map_view.undo()
        if restored is None:
            self.statusBar().showMessage("Nothing to undo", 2500)
            return
        self.world = restored
        self.layer_panel.set_world(self.world)
        self.map_view.set_tilesets(self.tilesets)
        self._on_active_layer_changed(min(self.layer_panel.current_array_index(), len(self.world.layers) - 1))
        self._on_map_modified()
        self.statusBar().showMessage("Undo", 1000)

    def _on_tileset_changed(self, index: int) -> None:
        if index < 0 or index >= len(self.tilesets):
            return
        self.active_tileset_index = index
        tileset = self.tilesets[index]
        self.tileset_picker.set_tileset(tileset)
        if index in self.tileset_selections:
            self.tileset_picker.set_selection(self.tileset_selections[index])
        else:
            self.tileset_selections[index] = QRect(0, 0, 1, 1)
            self.tileset_picker.set_selection(self.tileset_selections[index])
        self._rebuild_stamp_from_selection()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.matches(QKeySequence.Undo):
            self.on_undo()
            return
        key = event.key()
        if key == Qt.Key_P:
            self.pencil_action.setChecked(True)
            self._set_tool(ToolType.PENCIL)
            self.tiles_mode_action.setChecked(True)
            self._set_mode("tiles")
        elif key == Qt.Key_B:
            self.bucket_action.setChecked(True)
            self._set_tool(ToolType.BUCKET)
            self.tiles_mode_action.setChecked(True)
            self._set_mode("tiles")
        elif key == Qt.Key_A and not (event.modifiers() & Qt.ControlModifier):
            self.auto_tile_action.setChecked(not self.auto_tile_action.isChecked())
        elif key == Qt.Key_T:
            self.tiles_mode_action.setChecked(True)
            self._set_mode("tiles")
        elif key == Qt.Key_O:
            self.objects_mode_action.setChecked(True)
            self._set_mode("objects")
        else:
            super().keyPressEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    apply_dark_palette(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
