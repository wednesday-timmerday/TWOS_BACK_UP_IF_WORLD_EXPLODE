from __future__ import annotations

import os
import re
import sys
import traceback
from collections import deque
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from PySide6.QtCore import (
    QSettings,
    QStandardPaths,
    QTimer,
    Qt,
    QRect,
    QRectF,
    QSize,
    QPoint,
    QPointF,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QFont,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSizePolicy,
    QSpinBox,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QSplitter,
)


# --------------------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------------------

APP_ORG = "TWOS"
APP_NAME = "TilemapEditor"
RECOVERY_FILE = "autosave_recovery.world"
MAX_RECENTS = 10
ZOOM_LEVELS = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0]
DEFAULT_TILE_W = 16
DEFAULT_TILE_H = 16
EMPTY_TOKEN = "0"
TOKEN_RE = re.compile(r"^([a-zA-Z]+)(\d+)$")


class Tool(Enum):
    SINGLE = "single"
    RECTANGLE = "rectangle"
    ERASE = "erase"
    FILL = "fill"
    EYEDROPPER = "eyedropper"
    SELECTION = "selection"


# --------------------------------------------------------------------------------------
# Core data model — kept free of any Qt *widget* dependencies where practical so the
# .world read/write logic can be exercised without a display.
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class TileRef:
    """A single placed tile: which lettered tileset, and which index within it (0-based,
    matching world_loader.py's ``tiles[idx]`` indexing). ``None`` letter means empty."""

    letter: str = ""
    index: int = -1

    def is_empty(self) -> bool:
        return not self.letter

    def token(self) -> str:
        if self.is_empty():
            return EMPTY_TOKEN
        return f"{self.letter}{self.index}"

    @staticmethod
    def from_token(token: str) -> "TileRef":
        token = token.strip()
        if not token or token == EMPTY_TOKEN:
            return EMPTY_TILE
        m = TOKEN_RE.match(token)
        if not m:
            return EMPTY_TILE
        return TileRef(m.group(1), int(m.group(2)))


EMPTY_TILE = TileRef("", -1)


@dataclass
class SelectionRegion:
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    def is_valid(self) -> bool:
        return self.width > 0 and self.height > 0

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    @staticmethod
    def from_dict(data: Any) -> "SelectionRegion":
        if not isinstance(data, dict):
            return SelectionRegion()
        return SelectionRegion(int(data.get("x", 0)), int(data.get("y", 0)), int(data.get("width", 0)), int(data.get("height", 0)))


@dataclass
class Camera:
    x: float = 0.0
    y: float = 0.0
    zoom_index: int = 2

    @property
    def zoom(self) -> float:
        return ZOOM_LEVELS[max(0, min(self.zoom_index, len(ZOOM_LEVELS) - 1))]

    def set_zoom_index(self, index: int) -> None:
        self.zoom_index = max(0, min(index, len(ZOOM_LEVELS) - 1))

    def set_zoom_to_factor(self, factor: float) -> None:
        best = min(range(len(ZOOM_LEVELS)), key=lambda i: abs(ZOOM_LEVELS[i] - factor))
        self.zoom_index = best


class UndoAction:
    def __init__(self, description: str, undo: Callable[[], None], redo: Callable[[], None]):
        self.description = description
        self.undo = undo
        self.redo = redo


class UndoManager:
    def __init__(self, limit: int = 100) -> None:
        self.limit = max(1, limit)
        self._undo_stack: list[UndoAction] = []
        self._redo_stack: list[UndoAction] = []

    def clear(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()

    def push(self, action: UndoAction) -> None:
        self._undo_stack.append(action)
        if len(self._undo_stack) > self.limit:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def undo(self) -> Optional[str]:
        if not self._undo_stack:
            return None
        action = self._undo_stack.pop()
        action.undo()
        self._redo_stack.append(action)
        return action.description

    def redo(self) -> Optional[str]:
        if not self._redo_stack:
            return None
        action = self._redo_stack.pop()
        action.redo()
        self._undo_stack.append(action)
        return action.description


class TileLayer:
    """One layer of TileRefs, stored flat in row-major (x + y*width) order for easy
    random access. Token order for the .world file is column-major and is produced
    separately by WorldFileIO to match world_loader.py exactly."""

    def __init__(self, width: int, height: int, name: str = "Layer 1", visible: bool = True, locked: bool = False) -> None:
        self.name = name
        self.visible = visible
        self.locked = locked
        self.width = int(width)
        self.height = int(height)
        self.cells: list[TileRef] = [EMPTY_TILE] * max(0, self.width * self.height)

    def index(self, x: int, y: int) -> int:
        return y * self.width + x

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def get(self, x: int, y: int) -> TileRef:
        return self.cells[self.index(x, y)]

    def get_by_index(self, idx: int) -> TileRef:
        return self.cells[idx]

    def set_cell(self, x: int, y: int, ref: TileRef) -> TileRef:
        idx = self.index(x, y)
        old = self.cells[idx]
        self.cells[idx] = ref
        return old

    def set_by_index(self, idx: int, ref: TileRef) -> TileRef:
        old = self.cells[idx]
        self.cells[idx] = ref
        return old

    def clone(self) -> "TileLayer":
        layer = TileLayer(self.width, self.height, self.name, self.visible, self.locked)
        layer.cells = self.cells.copy()
        return layer


class TileMap:
    def __init__(self, width: int, height: int, tile_w: int, tile_h: int, layers: Optional[list[TileLayer]] = None) -> None:
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.tile_w = max(1, int(tile_w))
        self.tile_h = max(1, int(tile_h))
        self.layers = layers if layers is not None else [TileLayer(self.width, self.height, "Layer 1")]

    def create_default_layer(self) -> None:
        self.layers = [TileLayer(self.width, self.height, "Layer 1")]


# --------------------------------------------------------------------------------------
# .world file format — mirrors the parser in world_loader.py's load_world_file /
# _render_world_layer exactly (including the column-major token order and the
# "letters immediately followed by digits" token grammar).
# --------------------------------------------------------------------------------------


class WorldFormatError(ValueError):
    pass


class WorldFileIO:
    @staticmethod
    def write(path: str, tile_map: TileMap) -> None:
        lines = [
            f"TOTAL_LAYERS = {len(tile_map.layers)}",
            f"TILE_W = {tile_map.tile_w}",
            f"TILE_H = {tile_map.tile_h}",
            f"WORLD_W = {tile_map.width}",
            f"WORLD_H = {tile_map.height}",
            "",
        ]
        for n, layer in enumerate(tile_map.layers, start=1):
            lines.append(f"LAYER{n}:")
            tokens = []
            # Column-major to match world_loader.py: i = x * world_h + y
            for x in range(tile_map.width):
                for y in range(tile_map.height):
                    tokens.append(layer.get(x, y).token())
            lines.append("$".join(tokens) + "$")
            lines.append("")
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    @staticmethod
    def read(path: str) -> TileMap:
        with open(path, "r", encoding="utf-8") as f:
            raw_lines = f.readlines()

        meta: dict[str, Any] = {"layers": {}}
        current_layer: Optional[str] = None
        buffer = ""

        for line in raw_lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("TOTAL_LAYERS"):
                meta["total_layers"] = int(line.split("=", 1)[1].split("#")[0].strip())
            elif line.startswith("TILE_W"):
                meta["tile_w"] = int(line.split("=", 1)[1].split("#")[0].strip())
            elif line.startswith("TILE_H"):
                meta["tile_h"] = int(line.split("=", 1)[1].split("#")[0].strip())
            elif line.startswith("WORLD_W"):
                meta["world_w"] = int(line.split("=", 1)[1].split("#")[0].strip())
            elif line.startswith("WORLD_H"):
                meta["world_h"] = int(line.split("=", 1)[1].split("#")[0].strip())
            elif line.upper().startswith("LAYER") and line.endswith(":"):
                if current_layer is not None:
                    meta["layers"][current_layer] = buffer
                current_layer = line[:-1].upper()
                buffer = ""
            elif current_layer is not None:
                buffer += line.split("#")[0].strip()
        if current_layer is not None:
            meta["layers"][current_layer] = buffer

        for required in ("total_layers", "tile_w", "tile_h", "world_w", "world_h"):
            if required not in meta:
                raise WorldFormatError(f"Missing {required.upper()} in .world file.")

        world_w = meta["world_w"]
        world_h = meta["world_h"]
        if world_w <= 0 or world_h <= 0 or meta["tile_w"] <= 0 or meta["tile_h"] <= 0:
            raise WorldFormatError("Invalid world dimensions or tile size.")

        tile_map = TileMap(world_w, world_h, meta["tile_w"], meta["tile_h"], layers=[])
        for n in range(1, meta["total_layers"] + 1):
            key = f"LAYER{n}"
            raw = meta["layers"].get(key, "")
            tokens = [t for t in raw.split("$") if t != ""]
            layer = TileLayer(world_w, world_h, f"Layer {n}")
            # Column-major, matching world_loader.py: i = x * world_h + y
            for x in range(world_w):
                for y in range(world_h):
                    i = x * world_h + y
                    token = tokens[i] if i < len(tokens) else EMPTY_TOKEN
                    layer.set_cell(x, y, TileRef.from_token(token))
            tile_map.layers.append(layer)
        if not tile_map.layers:
            tile_map.layers.append(TileLayer(world_w, world_h, "Layer 1"))
        return tile_map


# --------------------------------------------------------------------------------------
# Tileset library — one lettered PNG per tileset, sliced into tiles, matching
# world_loader.py's _load_all_tilesets (every *.png in a directory, keyed by filename
# stem, sliced row-major by TILE_W x TILE_H).
# --------------------------------------------------------------------------------------


class Tileset:
    def __init__(self, letter: str, path: str, image: QImage, tile_w: int, tile_h: int) -> None:
        self.letter = letter
        self.path = path
        self.image = image
        self.tile_w = tile_w
        self.tile_h = tile_h
        self.columns = max(1, image.width() // tile_w)
        self.rows = max(1, image.height() // tile_h)
        self.tiles: list[QImage] = []
        for row in range(self.rows):
            for col in range(self.columns):
                self.tiles.append(image.copy(col * tile_w, row * tile_h, tile_w, tile_h))

    def count(self) -> int:
        return len(self.tiles)

    def tile_image(self, index: int) -> Optional[QImage]:
        if 0 <= index < len(self.tiles):
            return self.tiles[index]
        return None


class TilesetLibrary:
    """Holds every lettered tileset loaded from a single directory, mirroring
    world_loader.py's tileset_path / _load_all_tilesets."""

    def __init__(self) -> None:
        self.directory: str = ""
        self.tile_w: int = DEFAULT_TILE_W
        self.tile_h: int = DEFAULT_TILE_H
        self.sets: dict[str, Tileset] = {}

    def is_loaded(self) -> bool:
        return bool(self.sets)

    def clear(self) -> None:
        self.directory = ""
        self.sets.clear()

    def letters(self) -> list[str]:
        return sorted(self.sets.keys())

    def load_directory(self, directory: str, tile_w: int, tile_h: int) -> tuple[list[str], list[str]]:
        """Returns (failed, unreferenceable) filenames: ``failed`` couldn't be sliced
        at all; ``unreferenceable`` loaded fine but have a name no .world token could
        ever address (the token grammar is letters-then-digits, e.g. "A12", so a
        tileset named "Tile1" is indistinguishable from letter "Tile" index 1 and can
        never be the *target* of a token)."""
        if tile_w <= 0 or tile_h <= 0:
            raise WorldFormatError("Tile size must be a positive integer.")
        directory_path = Path(directory)
        if not directory_path.is_dir():
            raise WorldFormatError(f"Not a directory: {directory}")
        pngs = sorted(p for p in directory_path.iterdir() if p.suffix.lower() == ".png")
        if not pngs:
            raise WorldFormatError("No .png tilesets found in that directory.")
        new_sets: dict[str, Tileset] = {}
        failed: list[str] = []
        unreferenceable: list[str] = []
        for png_path in pngs:
            letter = png_path.stem
            image = QImage(str(png_path))
            if image.isNull() or image.width() < tile_w or image.height() < tile_h:
                failed.append(png_path.name)
                continue
            new_sets[letter] = Tileset(letter, str(png_path), image, tile_w, tile_h)
            if not re.fullmatch(r"[A-Za-z]+", letter):
                unreferenceable.append(png_path.name)
        if not new_sets:
            raise WorldFormatError("None of the .png files could be sliced with that tile size.")
        self.directory = str(directory_path)
        self.tile_w = tile_w
        self.tile_h = tile_h
        self.sets = new_sets
        return failed, unreferenceable

    def tile_image(self, ref: TileRef) -> Optional[QImage]:
        if ref.is_empty():
            return None
        tileset = self.sets.get(ref.letter)
        if tileset is None:
            return None
        return tileset.tile_image(ref.index)

    def snapshot(self) -> dict[str, Any]:
        return {"directory": self.directory, "tile_w": self.tile_w, "tile_h": self.tile_h}

    def restore(self, snapshot: dict[str, Any]) -> None:
        directory = snapshot.get("directory", "")
        if directory:
            try:
                self.load_directory(directory, snapshot.get("tile_w", DEFAULT_TILE_W), snapshot.get("tile_h", DEFAULT_TILE_H))
                return
            except Exception:
                pass
        self.clear()


@dataclass
class StrokeChange:
    layer_index: int
    index: int
    old_ref: TileRef
    new_ref: TileRef


def bresenham(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    points = []
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        points.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return points


def transform_matrix(matrix: list[list[TileRef]]) -> list[list[TileRef]]:
    return [row[:] for row in matrix]


def nine_slice_matrix(source: list[list[TileRef]], width: int, height: int) -> list[list[TileRef]]:
    if not source or width <= 0 or height <= 0:
        return []
    sh = len(source)
    sw = len(source[0]) if source[0] else 0
    if sw == 0 or sh == 0:
        return []
    result = [[EMPTY_TILE for _ in range(width)] for _ in range(height)]

    def pick_x(dx: int) -> int:
        if sw == 1:
            return 0
        if dx == 0:
            return 0
        if dx == width - 1:
            return sw - 1
        if sw == 2:
            return 0 if (dx - 1) % 2 == 0 else 1
        return 1 + ((dx - 1) % (sw - 2))

    def pick_y(dy: int) -> int:
        if sh == 1:
            return 0
        if dy == 0:
            return 0
        if dy == height - 1:
            return sh - 1
        if sh == 2:
            return 0 if (dy - 1) % 2 == 0 else 1
        return 1 + ((dy - 1) % (sh - 2))

    for y in range(height):
        sy = pick_y(y)
        for x in range(width):
            sx = pick_x(x)
            result[y][x] = source[sy][sx]
    return result


def render_stamp_preview(library: TilesetLibrary, stamp: list[list[TileRef]]) -> Optional[QImage]:
    if not library.is_loaded() or not stamp:
        return None
    h = len(stamp)
    w = len(stamp[0]) if h else 0
    if w <= 0 or h <= 0:
        return None
    cell_w, cell_h = library.tile_w, library.tile_h
    image = QImage(w * cell_w, h * cell_h, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    for y, row in enumerate(stamp):
        for x, ref in enumerate(row):
            img = library.tile_image(ref)
            if img is not None:
                painter.drawImage(QRect(x * cell_w, y * cell_h, cell_w, cell_h), img)
    painter.end()
    return image


# --------------------------------------------------------------------------------------
# UI: New map / New tileset dialogs
# --------------------------------------------------------------------------------------


class NewMapDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None, defaults: Optional[dict[str, int]] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Map")
        self.setModal(True)
        defaults = defaults or {}
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 100000)
        self.width_spin.setValue(defaults.get("world_w", 64))
        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 100000)
        self.height_spin.setValue(defaults.get("world_h", 64))
        self.tile_w_spin = QSpinBox()
        self.tile_w_spin.setRange(1, 100000)
        self.tile_w_spin.setValue(defaults.get("tile_w", DEFAULT_TILE_W))
        self.tile_h_spin = QSpinBox()
        self.tile_h_spin.setRange(1, 100000)
        self.tile_h_spin.setValue(defaults.get("tile_h", DEFAULT_TILE_H))
        self.layers_spin = QSpinBox()
        self.layers_spin.setRange(1, 32)
        self.layers_spin.setValue(defaults.get("layers", 1))
        form.addRow("World Width (tiles)", self.width_spin)
        form.addRow("World Height (tiles)", self.height_spin)
        form.addRow("Tile Width (px)", self.tile_w_spin)
        form.addRow("Tile Height (px)", self.tile_h_spin)
        form.addRow("Layers", self.layers_spin)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[int, int, int, int, int]:
        return (
            self.width_spin.value(),
            self.height_spin.value(),
            self.tile_w_spin.value(),
            self.tile_h_spin.value(),
            self.layers_spin.value(),
        )


# --------------------------------------------------------------------------------------
# UI: Tile palette (one tab per lettered tileset)
# --------------------------------------------------------------------------------------


class TilePaletteCanvas(QWidget):
    def __init__(self, editor: "MainWindow", letter: str) -> None:
        super().__init__()
        self.editor = editor
        self.letter = letter
        self.setMouseTracking(True)
        self.dragging = False
        self.drag_start: Optional[QPoint] = None
        self.drag_current: Optional[QPoint] = None
        self.hover: Optional[QPoint] = None

    def tileset(self) -> Optional[Tileset]:
        return self.editor.tileset_library.sets.get(self.letter)

    def sizeHint(self) -> QSize:
        ts = self.tileset()
        if ts is None:
            return QSize(256, 256)
        cell = max(1, self.editor.tileset_library.tile_w * self.editor.palette_zoom)
        cell_h = max(1, self.editor.tileset_library.tile_h * self.editor.palette_zoom)
        return QSize(ts.columns * cell, ts.rows * cell_h)

    def update_size(self) -> None:
        self.setMinimumSize(self.sizeHint())
        self.resize(self.sizeHint())
        self.update()

    def cell_from_pos(self, pos: QPoint) -> tuple[int, int]:
        lib = self.editor.tileset_library
        cell_w = max(1, lib.tile_w * self.editor.palette_zoom)
        cell_h = max(1, lib.tile_h * self.editor.palette_zoom)
        return pos.x() // cell_w, pos.y() // cell_h

    def tile_rect(self, tx: int, ty: int) -> QRect:
        lib = self.editor.tileset_library
        cell_w = max(1, lib.tile_w * self.editor.palette_zoom)
        cell_h = max(1, lib.tile_h * self.editor.palette_zoom)
        return QRect(tx * cell_w, ty * cell_h, cell_w, cell_h)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        _paint_checkerboard(painter, self.rect(), 16)
        ts = self.tileset()
        if ts is None:
            painter.setPen(self.palette().color(self.foregroundRole()))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No tileset")
            return
        lib = self.editor.tileset_library
        cell_w = max(1, lib.tile_w * self.editor.palette_zoom)
        cell_h = max(1, lib.tile_h * self.editor.palette_zoom)
        for row in range(ts.rows):
            for col in range(ts.columns):
                index = row * ts.columns + col
                img = ts.tile_image(index)
                if img is None:
                    continue
                rect = QRect(col * cell_w, row * cell_h, cell_w, cell_h)
                painter.drawImage(rect, img)
                painter.setPen(QPen(QColor(40, 40, 40, 180), 1))
                painter.drawRect(rect.adjusted(0, 0, -1, -1))
                if cell_w >= 22:
                    painter.setPen(QColor(255, 255, 255, 170))
                    painter.setFont(QFont("Sans Serif", max(6, cell_w // 5)))
                    painter.drawText(rect.adjusted(2, 1, -2, -2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, str(index))
        sel = self.editor.palette_selection
        if self.editor.palette_selection_letter == self.letter and sel.is_valid():
            painter.setPen(QPen(QColor(255, 215, 0), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRect(sel.x * cell_w, sel.y * cell_h, sel.width * cell_w, sel.height * cell_h).adjusted(1, 1, -1, -1))
        if self.hover is not None:
            painter.setPen(QPen(QColor(100, 200, 255), 2))
            painter.drawRect(self.tile_rect(self.hover.x(), self.hover.y()).adjusted(1, 1, -1, -1))
        if self.dragging and self.drag_start and self.drag_current:
            r = self.drag_rect()
            painter.setPen(QPen(QColor(255, 255, 255), 2, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(255, 255, 255, 40))
            painter.drawRect(r.adjusted(1, 1, -1, -1))

    def drag_rect(self) -> QRect:
        if not (self.drag_start and self.drag_current):
            return QRect()
        a, b = self.drag_start, self.drag_current
        x1, x2 = sorted((a.x(), b.x()))
        y1, y2 = sorted((a.y(), b.y()))
        cell_w = max(1, self.editor.tileset_library.tile_w * self.editor.palette_zoom)
        cell_h = max(1, self.editor.tileset_library.tile_h * self.editor.palette_zoom)
        return QRect(x1 * cell_w, y1 * cell_h, (x2 - x1 + 1) * cell_w, (y2 - y1 + 1) * cell_h)

    def _clamped_cell(self, pos: QPoint) -> Optional[tuple[int, int]]:
        ts = self.tileset()
        if ts is None:
            return None
        tx, ty = self.cell_from_pos(pos)
        if 0 <= tx < ts.columns and 0 <= ty < ts.rows:
            return tx, ty
        return None

    def mousePressEvent(self, event) -> None:
        ts = self.tileset()
        if ts is None:
            return
        cell = self._clamped_cell(event.position().toPoint())
        if cell is None:
            return
        tx, ty = cell
        self.setFocus()
        self.editor.set_active_tileset_letter(self.letter)
        if self.editor.current_tool == Tool.RECTANGLE:
            self.dragging = True
            self.drag_start = QPoint(tx, ty)
            self.drag_current = QPoint(tx, ty)
            self.update()
            return
        self.editor.select_single_tile(self.letter, tx, ty)
        self.update()

    def mouseMoveEvent(self, event) -> None:
        ts = self.tileset()
        if ts is None:
            return
        pos = event.position().toPoint()
        tx, ty = self.cell_from_pos(pos)
        self.hover = QPoint(tx, ty) if (0 <= tx < ts.columns and 0 <= ty < ts.rows) else None
        if self.dragging and self.drag_start is not None:
            cx = max(0, min(tx, ts.columns - 1))
            cy = max(0, min(ty, ts.rows - 1))
            self.drag_current = QPoint(cx, cy)
            self.editor.set_palette_selection_region(self.letter, self.drag_start.x(), self.drag_start.y(), cx, cy)
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self.dragging and event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            self.drag_start = None
            self.drag_current = None
            self.editor.commit_palette_stamp_selection()
            self.update()

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.editor.change_palette_zoom(1 if event.angleDelta().y() > 0 else -1)
            event.accept()
            return
        super().wheelEvent(event)


def _paint_checkerboard(painter: QPainter, rect: QRect, size: int, c1: QColor = QColor(80, 80, 80), c2: QColor = QColor(100, 100, 100)) -> None:
    y = rect.top()
    toggle = False
    while y < rect.bottom() + size:
        x = rect.left()
        row_toggle = toggle
        while x < rect.right() + size:
            painter.fillRect(QRect(x, y, size, size), c1 if row_toggle else c2)
            row_toggle = not row_toggle
            x += size
        toggle = not toggle
        y += size


class TilePalette(QWidget):
    """Tabbed palette: one tab per lettered tileset, matching world_loader.py's
    directory-of-PNGs tileset model."""

    def __init__(self, editor: "MainWindow") -> None:
        super().__init__()
        self.editor = editor
        self.canvases: dict[str, TilePaletteCanvas] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        top = QHBoxLayout()
        self.single_preview = QLabel("Tile")
        self.single_preview.setFixedSize(72, 72)
        self.single_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.single_preview.setFrameShape(QFrame.Shape.StyledPanel)
        self.rect_preview = QLabel("Stamp")
        self.rect_preview.setFixedSize(72, 72)
        self.rect_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rect_preview.setFrameShape(QFrame.Shape.StyledPanel)
        self.selected_label = QLabel("Selected: -")
        self.selected_label.setWordWrap(True)
        top.addWidget(self.single_preview)
        top.addWidget(self.rect_preview)
        top.addWidget(self.selected_label, 1)
        layout.addLayout(top)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs, 1)

        self.empty_label = QLabel("Load a tileset folder\n(File \u2192 Load Tileset Folder...)")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label)
        self.empty_label.hide()

    def _on_tab_changed(self, index: int) -> None:
        if index < 0:
            return
        letter = self.tabs.tabText(index)
        if letter:
            self.editor.set_active_tileset_letter(letter, refresh=False)

    def rebuild_tabs(self) -> None:
        self.tabs.blockSignals(True)
        self.tabs.clear()
        self.canvases.clear()
        letters = self.editor.tileset_library.letters()
        self.empty_label.setVisible(not letters)
        self.tabs.setVisible(bool(letters))
        for letter in letters:
            canvas = TilePaletteCanvas(self.editor, letter)
            scroll = QScrollArea()
            scroll.setWidgetResizable(False)
            scroll.setWidget(canvas)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            self.canvases[letter] = canvas
            self.tabs.addTab(scroll, letter)
        if letters:
            active = self.editor.active_tileset_letter if self.editor.active_tileset_letter in letters else letters[0]
            self.tabs.setCurrentIndex(letters.index(active))
        self.tabs.blockSignals(False)

    def refresh(self) -> None:
        for canvas in self.canvases.values():
            canvas.update_size()
            canvas.update()
        self.update_previews()

    def update_previews(self) -> None:
        lib = self.editor.tileset_library
        self.single_preview.setPixmap(QPixmap())
        self.single_preview.setText("Tile")
        self.rect_preview.setPixmap(QPixmap())
        self.rect_preview.setText("Stamp")
        ref = self.editor.selected_ref
        if lib.is_loaded() and not ref.is_empty():
            img = lib.tile_image(ref)
            if img is not None:
                pm = QPixmap.fromImage(img).scaled(self.single_preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.single_preview.setPixmap(pm)
                self.single_preview.setText("")
            self.selected_label.setText(f"Selected: {ref.token()}")
        else:
            self.selected_label.setText("Selected: -")
        stamp = self.editor.current_stamp_matrix()
        if stamp and lib.is_loaded():
            preview = render_stamp_preview(lib, stamp)
            if preview is not None:
                pm = QPixmap.fromImage(preview).scaled(self.rect_preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.rect_preview.setPixmap(pm)
                self.rect_preview.setText("")


# --------------------------------------------------------------------------------------
# UI: Layers
# --------------------------------------------------------------------------------------


class LayerRowWidget(QWidget):
    def __init__(self, editor: "MainWindow", index: int) -> None:
        super().__init__()
        self.editor = editor
        self.index = index
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        self.vis_btn = QToolButton()
        self.vis_btn.setCheckable(True)
        self.vis_btn.setToolTip("Toggle layer visibility")
        self.vis_btn.clicked.connect(self.on_visibility)
        self.lock_btn = QToolButton()
        self.lock_btn.setCheckable(True)
        self.lock_btn.setToolTip("Lock layer against edits")
        self.lock_btn.clicked.connect(self.on_lock)
        self.name_label = QLabel()
        self.name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.vis_btn)
        layout.addWidget(self.lock_btn)
        layout.addWidget(self.name_label, 1)
        self.refresh()

    def refresh(self) -> None:
        layer = self.editor.map.layers[self.index]
        self.name_label.setText(layer.name)
        self.vis_btn.setText("\U0001F441" if layer.visible else "\U0001F576")
        self.vis_btn.setChecked(layer.visible)
        self.lock_btn.setText("\U0001F512" if layer.locked else "\U0001F513")
        self.lock_btn.setChecked(layer.locked)
        self.setStyleSheet("background: rgba(120,160,220,45);" if self.index == self.editor.active_layer_index else "")

    def on_visibility(self) -> None:
        self.editor.set_layer_visibility(self.index, self.vis_btn.isChecked())

    def on_lock(self) -> None:
        self.editor.set_layer_locked(self.index, self.lock_btn.isChecked())


class LayerPanel(QWidget):
    def __init__(self, editor: "MainWindow") -> None:
        super().__init__()
        self.editor = editor
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(QLabel("Layers"))
        btns = QHBoxLayout()
        self.add_btn = QPushButton("Add")
        self.del_btn = QPushButton("Delete")
        self.dup_btn = QPushButton("Duplicate")
        self.up_btn = QPushButton("\u2191")
        self.down_btn = QPushButton("\u2193")
        self.rename_btn = QPushButton("Rename")
        for b in [self.add_btn, self.del_btn, self.dup_btn, self.up_btn, self.down_btn, self.rename_btn]:
            btns.addWidget(b)
        layout.addLayout(btns)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.on_active_changed)
        layout.addWidget(self.list, 1)
        self.add_btn.clicked.connect(self.editor.add_layer)
        self.del_btn.clicked.connect(self.editor.delete_current_layer)
        self.dup_btn.clicked.connect(self.editor.duplicate_current_layer)
        self.up_btn.clicked.connect(lambda: self.editor.move_layer(-1))
        self.down_btn.clicked.connect(lambda: self.editor.move_layer(1))
        self.rename_btn.clicked.connect(self.editor.rename_current_layer)

    def on_active_changed(self, row: int) -> None:
        if row >= 0:
            self.editor.set_active_layer(row)

    def refresh(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for i in range(len(self.editor.map.layers)):
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 32))
            self.list.addItem(item)
            widget = LayerRowWidget(self.editor, i)
            self.list.setItemWidget(item, widget)
        if 0 <= self.editor.active_layer_index < self.list.count():
            self.list.setCurrentRow(self.editor.active_layer_index)
        self.list.blockSignals(False)

    def update_rows(self) -> None:
        for i in range(self.list.count()):
            widget = self.list.itemWidget(self.list.item(i))
            if isinstance(widget, LayerRowWidget):
                widget.refresh()


class EditorStatusBar(QStatusBar):
    def __init__(self, editor: "MainWindow") -> None:
        super().__init__()
        self.editor = editor
        self.mouse_label = QLabel("Tile: - | Pixel: -")
        self.layer_label = QLabel("Layer: -")
        self.tile_label = QLabel("Selected: -")
        self.zoom_label = QLabel("Zoom: 100%")
        self.tool_label = QLabel("Tool: -")
        self.map_label = QLabel("Map: -")
        self.tileset_label = QLabel("Tilesets: none")
        for lbl in [self.mouse_label, self.layer_label, self.tile_label, self.zoom_label, self.tool_label, self.map_label, self.tileset_label]:
            self.addPermanentWidget(lbl)

    def update_all(self) -> None:
        editor = self.editor
        self.mouse_label.setText(f"Tile: {editor.hover_tile_text} | Pixel: {editor.hover_pixel_text}")
        self.layer_label.setText(f"Layer: {editor.active_layer_name()}")
        self.tile_label.setText(f"Selected: {editor.selected_ref.token() if not editor.selected_ref.is_empty() else '-'}")
        self.zoom_label.setText(f"Zoom: {int(editor.camera.zoom * 100)}%")
        self.tool_label.setText(f"Tool: {editor.current_tool.value}")
        self.map_label.setText(f"Map: {editor.map.width}x{editor.map.height} @ {editor.map.tile_w}x{editor.map.tile_h}")
        if editor.tileset_library.is_loaded():
            n = len(editor.tileset_library.sets)
            self.tileset_label.setText(f"Tilesets: {n} loaded ({', '.join(editor.tileset_library.letters())})")
        else:
            self.tileset_label.setText("Tilesets: none")


# --------------------------------------------------------------------------------------
# UI: Map canvas
# --------------------------------------------------------------------------------------


class MapView(QWidget):
    def __init__(self, editor: "MainWindow") -> None:
        super().__init__()
        self.editor = editor
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.dragging_pan = False
        self.dragging_stroke = False
        self.dragging_rect = False
        self.dragging_select = False
        self.space_down = False
        self.last_mouse_pos = QPointF(0, 0)
        self.stroke_changes: list[StrokeChange] = []
        self.stroke_seen: set[int] = set()
        self.stroke_last_cell: Optional[QPoint] = None
        self.pan_anchor = QPointF(0, 0)
        self.pan_start = QPointF(0, 0)
        self.rect_start: Optional[QPoint] = None
        self.rect_current: Optional[QPoint] = None
        self.selection_start: Optional[QPoint] = None
        self.selection_current: Optional[QPoint] = None

    def sizeHint(self) -> QSize:
        return QSize(1200, 800)

    def world_to_view(self, px: float, py: float) -> QPointF:
        zoom = self.editor.camera.zoom
        return QPointF((px - self.editor.camera.x) * zoom, (py - self.editor.camera.y) * zoom)

    def view_to_world(self, vx: float, vy: float) -> QPointF:
        zoom = self.editor.camera.zoom
        return QPointF(vx / zoom + self.editor.camera.x, vy / zoom + self.editor.camera.y)

    def mouse_tile(self, pos: QPointF) -> Optional[QPoint]:
        world = self.view_to_world(pos.x(), pos.y())
        tw, th = self.editor.map.tile_w, self.editor.map.tile_h
        x = int(world.x() // tw)
        y = int(world.y() // th)
        if 0 <= x < self.editor.map.width and 0 <= y < self.editor.map.height:
            return QPoint(x, y)
        return None

    def mouse_pixels(self, pos: QPointF) -> tuple[int, int]:
        world = self.view_to_world(pos.x(), pos.y())
        return int(world.x()), int(world.y())

    def tile_rect(self, tx: int, ty: int) -> QRectF:
        tw, th = self.editor.map.tile_w, self.editor.map.tile_h
        zoom = self.editor.camera.zoom
        x = (tx * tw - self.editor.camera.x) * zoom
        y = (ty * th - self.editor.camera.y) * zoom
        return QRectF(x, y, tw * zoom, th * zoom)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self._paint_background(painter)
        map_model = self.editor.map
        lib = self.editor.tileset_library
        zoom = self.editor.camera.zoom
        tw, th = map_model.tile_w, map_model.tile_h
        view_rect = self.rect()
        world_left = self.editor.camera.x
        world_top = self.editor.camera.y
        world_right = world_left + view_rect.width() / zoom
        world_bottom = world_top + view_rect.height() / zoom
        x0 = max(0, int(world_left // tw) - 1)
        y0 = max(0, int(world_top // th) - 1)
        x1 = min(map_model.width, int(world_right // tw) + 2)
        y1 = min(map_model.height, int(world_bottom // th) + 2)
        for layer in map_model.layers:
            if not layer.visible:
                continue
            for y in range(y0, y1):
                base = y * layer.width
                for x in range(x0, x1):
                    ref = layer.cells[base + x]
                    if ref.is_empty():
                        continue
                    img = lib.tile_image(ref) if lib.is_loaded() else None
                    if img is None:
                        continue
                    rect = QRectF((x * tw - self.editor.camera.x) * zoom, (y * th - self.editor.camera.y) * zoom, tw * zoom, th * zoom)
                    painter.drawImage(rect, img)
        if self.editor.grid_visible:
            self._paint_grid(painter, x0, y0, x1, y1)
        if self.editor.map_selection.is_valid():
            self._paint_region_outline(painter, self.editor.map_selection, QColor(255, 215, 0), Qt.PenStyle.DashLine)
        hover = self.editor.hover_tile
        if hover is not None:
            self._paint_region_outline(painter, SelectionRegion(hover.x(), hover.y(), 1, 1), QColor(100, 200, 255), Qt.PenStyle.SolidLine)
        if self.dragging_rect and self.rect_start and self.rect_current:
            r = self.dragged_region()
            self._paint_region_outline(painter, r, QColor(255, 255, 255), Qt.PenStyle.DashLine, fill=QColor(255, 255, 255, 30))
            self._paint_stamp_preview(painter, r)
        elif self.editor.current_tool == Tool.SINGLE and self.editor.hover_tile is not None and self.editor.brush_stamp_available():
            self._paint_stamp_at_hover(painter, self.editor.hover_tile.x(), self.editor.hover_tile.y(), 0.35)
        elif self.editor.current_tool == Tool.RECTANGLE and self.editor.hover_tile is not None and self.editor.brush_stamp_available() and not self.dragging_rect:
            self._paint_stamp_at_hover(painter, self.editor.hover_tile.x(), self.editor.hover_tile.y(), 0.20)
        if self.dragging_select and self.selection_start and self.selection_current:
            r = self.selected_region()
            self._paint_region_outline(painter, r, QColor(100, 255, 100), Qt.PenStyle.DashLine, fill=QColor(100, 255, 100, 40))
        painter.end()

    def _paint_background(self, painter: QPainter) -> None:
        editor = self.editor
        if editor.checkerboard_background:
            _paint_checkerboard(painter, self.rect(), 16, QColor(54, 54, 54), QColor(65, 65, 65))
        else:
            painter.fillRect(self.rect(), editor.background_color)

    def _paint_grid(self, painter: QPainter, x0: int, y0: int, x1: int, y1: int) -> None:
        map_model = self.editor.map
        tw, th = map_model.tile_w, map_model.tile_h
        zoom = self.editor.camera.zoom
        painter.setPen(QPen(self.editor.grid_color, 1))
        for x in range(x0, x1 + 1):
            sx = (x * tw - self.editor.camera.x) * zoom
            painter.drawLine(int(sx), 0, int(sx), self.height())
        for y in range(y0, y1 + 1):
            sy = (y * th - self.editor.camera.y) * zoom
            painter.drawLine(0, int(sy), self.width(), int(sy))

    def _paint_region_outline(self, painter: QPainter, region: SelectionRegion, color: QColor, style: Qt.PenStyle, fill: Optional[QColor] = None) -> None:
        if not region.is_valid():
            return
        tw, th = self.editor.map.tile_w, self.editor.map.tile_h
        zoom = self.editor.camera.zoom
        rect = QRectF((region.x * tw - self.editor.camera.x) * zoom, (region.y * th - self.editor.camera.y) * zoom, region.width * tw * zoom, region.height * th * zoom)
        painter.setPen(QPen(color, 2, style))
        painter.setBrush(fill if fill is not None else Qt.BrushStyle.NoBrush)
        painter.drawRect(rect.adjusted(1, 1, -1, -1))

    def _paint_stamp_preview(self, painter: QPainter, region: SelectionRegion) -> None:
        if not region.is_valid() or not self.editor.brush_stamp_available():
            return
        stamp = self.editor.current_stamp_matrix()
        if not stamp:
            return
        sized = nine_slice_matrix(stamp, region.width, region.height) if self.editor.current_tool == Tool.RECTANGLE else stamp
        if not sized:
            return
        self._paint_matrix_preview(painter, region.x, region.y, sized, 0.45)

    def _paint_stamp_at_hover(self, painter: QPainter, tile_x: int, tile_y: int, alpha: float) -> None:
        stamp = self.editor.current_stamp_matrix()
        if not stamp:
            return
        if self.editor.current_tool == Tool.RECTANGLE:
            self._paint_matrix_preview(painter, tile_x, tile_y, stamp, alpha)
        else:
            self._paint_matrix_preview(painter, tile_x, tile_y, [[self.editor.selected_ref]], alpha)

    def _paint_matrix_preview(self, painter: QPainter, x: int, y: int, matrix: list[list[TileRef]], alpha: float) -> None:
        lib = self.editor.tileset_library
        if not lib.is_loaded():
            return
        tw, th = self.editor.map.tile_w, self.editor.map.tile_h
        zoom = self.editor.camera.zoom
        painter.save()
        painter.setOpacity(alpha)
        for yy, row in enumerate(matrix):
            for xx, ref in enumerate(row):
                if ref.is_empty():
                    continue
                img = lib.tile_image(ref)
                if img is None:
                    continue
                rect = QRectF(((x + xx) * tw - self.editor.camera.x) * zoom, ((y + yy) * th - self.editor.camera.y) * zoom, tw * zoom, th * zoom)
                painter.drawImage(rect, img)
        painter.restore()

    def selected_region(self) -> SelectionRegion:
        if not (self.selection_start and self.selection_current):
            return SelectionRegion()
        x1, x2 = sorted((self.selection_start.x(), self.selection_current.x()))
        y1, y2 = sorted((self.selection_start.y(), self.selection_current.y()))
        return SelectionRegion(x1, y1, x2 - x1 + 1, y2 - y1 + 1)

    def dragged_region(self) -> SelectionRegion:
        if not (self.rect_start and self.rect_current):
            return SelectionRegion()
        x1, x2 = sorted((self.rect_start.x(), self.rect_current.x()))
        y1, y2 = sorted((self.rect_start.y(), self.rect_current.y()))
        return SelectionRegion(x1, y1, x2 - x1 + 1, y2 - y1 + 1)

    def mousePressEvent(self, event) -> None:
        self.setFocus()
        self.last_mouse_pos = event.position()
        mouse_tile = self.mouse_tile(event.position())
        if event.button() == Qt.MouseButton.MiddleButton or (event.button() == Qt.MouseButton.LeftButton and self.space_down):
            self.dragging_pan = True
            self.pan_start = event.position()
            self.pan_anchor = QPointF(self.editor.camera.x, self.editor.camera.y)
            return
        if mouse_tile is None:
            return
        if event.button() == Qt.MouseButton.RightButton:
            self.editor.erase_cell(mouse_tile.x(), mouse_tile.y(), record_undo=True)
            return
        tool = self.editor.current_tool
        layer = self.editor.active_layer()
        if layer is None or layer.locked or not layer.visible:
            return
        if tool in (Tool.SINGLE, Tool.ERASE):
            self.dragging_stroke = True
            self.stroke_changes = []
            self.stroke_seen = set()
            self.stroke_last_cell = mouse_tile
            if tool == Tool.ERASE:
                self.editor.paint_cell(mouse_tile.x(), mouse_tile.y(), EMPTY_TILE, self.stroke_changes, self.stroke_seen)
            else:
                self.editor.paint_current_brush_at(mouse_tile.x(), mouse_tile.y(), self.stroke_changes, self.stroke_seen)
            self.update_cell_region(mouse_tile.x(), mouse_tile.y())
            return
        if tool == Tool.FILL:
            self.editor.flood_fill(mouse_tile.x(), mouse_tile.y())
            return
        if tool == Tool.EYEDROPPER:
            self.editor.pick_from_map(mouse_tile.x(), mouse_tile.y())
            return
        if tool == Tool.RECTANGLE:
            self.dragging_rect = True
            self.rect_start = mouse_tile
            self.rect_current = mouse_tile
            return
        if tool == Tool.SELECTION:
            self.dragging_select = True
            self.selection_start = mouse_tile
            self.selection_current = mouse_tile
            self.editor.map_selection = SelectionRegion(mouse_tile.x(), mouse_tile.y(), 1, 1)
            return

    def mouseMoveEvent(self, event) -> None:
        self.last_mouse_pos = event.position()
        tile = self.mouse_tile(event.position())
        if tile is not None:
            self.editor.hover_tile = tile
            self.editor.hover_pixel = self.mouse_pixels(event.position())
        else:
            self.editor.hover_tile = None
            self.editor.hover_pixel = None
        if self.dragging_pan:
            delta = event.position() - self.pan_start
            self.editor.camera.x = max(0.0, self.pan_anchor.x() - delta.x() / self.editor.camera.zoom)
            self.editor.camera.y = max(0.0, self.pan_anchor.y() - delta.y() / self.editor.camera.zoom)
            self.editor.refresh_views()
            return
        if self.dragging_stroke and tile is not None and self.stroke_last_cell is not None:
            for pt in bresenham(self.stroke_last_cell.x(), self.stroke_last_cell.y(), tile.x(), tile.y()):
                if self.editor.current_tool == Tool.ERASE:
                    self.editor.paint_cell(pt[0], pt[1], EMPTY_TILE, self.stroke_changes, self.stroke_seen)
                else:
                    self.editor.paint_current_brush_at(pt[0], pt[1], self.stroke_changes, self.stroke_seen)
            self.stroke_last_cell = tile
            self.update()
            self.editor.refresh_status()
            return
        if self.dragging_rect and tile is not None:
            self.rect_current = tile
            self.update()
            return
        if self.dragging_select and tile is not None:
            self.selection_current = tile
            self.editor.map_selection = self.selected_region()
            self.update()
            return
        self.editor.refresh_status()
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton or (event.button() == Qt.MouseButton.LeftButton and self.space_down):
            self.dragging_pan = False
            return
        if self.dragging_stroke and event.button() == Qt.MouseButton.LeftButton:
            self.dragging_stroke = False
            if self.stroke_changes:
                self.editor.commit_stroke(self.stroke_changes, "Paint")
            self.stroke_changes = []
            self.stroke_seen = set()
            self.stroke_last_cell = None
            return
        if self.dragging_rect and event.button() == Qt.MouseButton.LeftButton:
            region = self.dragged_region()
            self.dragging_rect = False
            if self.rect_start and self.rect_current and self.editor.brush_stamp_available():
                self.editor.commit_rectangle_stamp(region)
            self.rect_start = None
            self.rect_current = None
            self.update()
            return
        if self.dragging_select and event.button() == Qt.MouseButton.LeftButton:
            self.dragging_select = False
            self.editor.map_selection = self.selected_region()
            self.editor.refresh_views()
            return

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.editor.zoom_at_cursor(event.position(), 1 if event.angleDelta().y() > 0 else -1)
            event.accept()
            return
        delta = event.angleDelta().y()
        self.editor.camera.y = max(0.0, self.editor.camera.y - delta / 2.0 / self.editor.camera.zoom)
        self.editor.refresh_views()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space:
            self.space_down = True
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space:
            self.space_down = False
            return
        super().keyReleaseEvent(event)

    def update_cell_region(self, x: int, y: int) -> None:
        rect = self.tile_rect(x, y).toAlignedRect().adjusted(-2, -2, 2, 2)
        self.update(rect)


# --------------------------------------------------------------------------------------
# File/session management. The .world file is the single source of truth for tile data
# (and is what world_loader.py reads). A small "<mapfile>.editor.json" sidecar next to
# it remembers editor-only state — camera, grid, last tool, tileset folder — so re-
# opening a map restores your view without touching the .world format at all.
# --------------------------------------------------------------------------------------

import json


class FileManager:
    @staticmethod
    def app_data_dir() -> Path:
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        if not base:
            base = str(Path.home() / ".tilemap_editor")
        path = Path(base)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def recovery_path() -> Path:
        return FileManager.app_data_dir() / RECOVERY_FILE

    @staticmethod
    def recovery_meta_path() -> Path:
        return FileManager.app_data_dir() / (RECOVERY_FILE + ".editor.json")

    @staticmethod
    def sidecar_path(world_path: str) -> Path:
        return Path(str(world_path) + ".editor.json")

    @staticmethod
    def save_sidecar(world_path: str, data: dict[str, Any]) -> None:
        try:
            with FileManager.sidecar_path(world_path).open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    @staticmethod
    def load_sidecar(world_path: str) -> dict[str, Any]:
        path = FileManager.sidecar_path(world_path)
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def save_recent(settings: QSettings, path: str) -> None:
        recents = [p for p in settings.value("recentFiles", [], list) if isinstance(p, str)]
        path = str(Path(path).resolve())
        recents = [p for p in recents if p != path]
        recents.insert(0, path)
        settings.setValue("recentFiles", recents[:MAX_RECENTS])

    @staticmethod
    def recent_files(settings: QSettings) -> list[str]:
        recents = settings.value("recentFiles", [], list)
        return [str(p) for p in recents if isinstance(p, str)]


# --------------------------------------------------------------------------------------
# Main window
# --------------------------------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setWindowTitle("Tilemap Editor")
        self.resize(1600, 1000)
        self.settings = QSettings(APP_ORG, APP_NAME)
        self.undo_manager = UndoManager(100)
        self.map = TileMap(64, 64, DEFAULT_TILE_W, DEFAULT_TILE_H)
        self.tileset_library = TilesetLibrary()
        self.camera = Camera()
        self.current_tool = Tool.SINGLE
        self.active_tileset_letter: str = ""
        self.selected_ref: TileRef = EMPTY_TILE
        self.palette_zoom = 2
        self.palette_selection = SelectionRegion(0, 0, 0, 0)
        self.palette_selection_letter: str = ""
        self.brush_selection: list[list[TileRef]] = []
        self.map_selection = SelectionRegion()
        self.hover_tile: Optional[QPoint] = None
        self.hover_pixel: Optional[tuple[int, int]] = None
        self.hover_tile_text = "-"
        self.hover_pixel_text = "-"
        self.grid_visible = True
        self.grid_color = QColor(80, 80, 80)
        self.background_color = QColor(30, 30, 30)
        self.checkerboard_background = True
        self.active_layer_index = 0
        self.modified = False
        self.current_file: str = ""
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(60000)
        self._autosave_timer.timeout.connect(self.autosave)
        self._autosave_timer.start()

        self._build_ui()
        self._build_actions()
        self._build_menus()
        self.apply_dark_theme()
        self.refresh_recent_menu()
        self.refresh_all()
        QTimer.singleShot(0, self.check_recovery)

    # -- UI construction ---------------------------------------------------------

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.palette_panel = TilePalette(self)
        self.map_view = MapView(self)
        self.layer_panel = LayerPanel(self)
        splitter.addWidget(self.palette_panel)
        splitter.addWidget(self.map_view)
        splitter.addWidget(self.layer_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([300, 1000, 260])
        self.setCentralWidget(splitter)
        self.toolbar = QToolBar("Toolbar")
        self.toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)
        self.status = EditorStatusBar(self)
        self.setStatusBar(self.status)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _make_action(self, text: str, slot: Callable[[], None], shortcut: Optional[str] = None, checkable: bool = False, tip: str = "") -> QAction:
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.setCheckable(checkable)
        if tip:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        return action

    def _build_actions(self) -> None:
        self.act_new = self._make_action("New Map...", self.new_map, "Ctrl+N", tip="Create a new .world map")
        self.act_open = self._make_action("Open Map (.world)...", self.open_map, "Ctrl+O")
        self.act_save = self._make_action("Save", self.save_map, "Ctrl+S")
        self.act_save_as = self._make_action("Save As...", self.save_map_as, "Ctrl+Shift+S")
        self.act_load_tileset = self._make_action("Load Tileset Folder...", self.load_tileset_folder, tip="Pick a folder of lettered PNG tilesets")
        self.act_change_tile_size = self._make_action("Change Tile Size...", self.change_tile_size)
        self.act_exit = self._make_action("Exit", self.close)
        self.act_undo = self._make_action("Undo", self.undo, "Ctrl+Z")
        self.act_redo = self._make_action("Redo", self.redo, "Ctrl+Y")

        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        self.act_single = self._make_action("Draw", lambda: self.set_tool(Tool.SINGLE), "I", checkable=True, tip="Draw single tiles/stamps (I)")
        self.act_rect = self._make_action("Rectangle", lambda: self.set_tool(Tool.RECTANGLE), "R", checkable=True, tip="Drag a stamped rectangle (R)")
        self.act_fill = self._make_action("Fill", lambda: self.set_tool(Tool.FILL), "F", checkable=True, tip="Flood fill (F)")
        self.act_eyedropper = self._make_action("Eyedropper", lambda: self.set_tool(Tool.EYEDROPPER), "E", checkable=True, tip="Pick a tile from the map (E)")
        self.act_erase = self._make_action("Erase", lambda: self.set_tool(Tool.ERASE), "B", checkable=True, tip="Erase (B)")
        self.act_selection = self._make_action("Select", lambda: self.set_tool(Tool.SELECTION), "S", checkable=True, tip="Select a region (S), Delete to clear")
        for a in [self.act_single, self.act_rect, self.act_fill, self.act_eyedropper, self.act_erase, self.act_selection]:
            self.tool_group.addAction(a)
        self.act_single.setChecked(True)

        self.act_grid = self._make_action("Grid", self.toggle_grid, "G", True)
        self.act_grid.setChecked(True)
        self.act_zoom_in = self._make_action("Zoom In", self.zoom_in, "Ctrl+=")
        self.act_zoom_out = self._make_action("Zoom Out", self.zoom_out, "Ctrl+-")
        self.act_reset_zoom = self._make_action("Reset Zoom", self.reset_zoom, "Ctrl+0")
        self.act_bg_color = self._make_action("Background Color...", self.pick_background_color)
        self.act_grid_color = self._make_action("Grid Color...", self.pick_grid_color)
        self.act_checkerboard = self._make_action("Checkerboard Background", self.toggle_checkerboard, checkable=True)
        self.act_checkerboard.setChecked(True)
        self.recent_menu = QMenu("Recent Files", self)

    def _build_menus(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("File")
        for a in [self.act_new, self.act_open, self.act_save, self.act_save_as, self.act_load_tileset, self.act_change_tile_size]:
            file_menu.addAction(a)
        file_menu.addMenu(self.recent_menu)
        file_menu.addSeparator()
        file_menu.addAction(self.act_exit)
        tools_menu = bar.addMenu("Tools")
        for a in [self.act_single, self.act_rect, self.act_fill, self.act_eyedropper, self.act_erase, self.act_selection]:
            tools_menu.addAction(a)
        view_menu = bar.addMenu("View")
        for a in [self.act_grid, self.act_zoom_in, self.act_zoom_out, self.act_reset_zoom, self.act_bg_color, self.act_grid_color, self.act_checkerboard]:
            view_menu.addAction(a)
        edit_menu = bar.addMenu("Edit")
        edit_menu.addAction(self.act_undo)
        edit_menu.addAction(self.act_redo)

        self.toolbar.addAction(self.act_new)
        self.toolbar.addAction(self.act_open)
        self.toolbar.addAction(self.act_save)
        self.toolbar.addAction(self.act_load_tileset)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.act_undo)
        self.toolbar.addAction(self.act_redo)
        self.toolbar.addSeparator()
        for a in [self.act_single, self.act_rect, self.act_fill, self.act_eyedropper, self.act_erase, self.act_selection]:
            self.toolbar.addAction(a)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.act_grid)
        self.toolbar.addAction(self.act_zoom_in)
        self.toolbar.addAction(self.act_zoom_out)
        self.toolbar.addAction(self.act_reset_zoom)

    def apply_dark_theme(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        apply_dark_theme(app)

    # -- refresh helpers -----------------------------------------------------------

    def refresh_all(self) -> None:
        self.refresh_views()
        self.layer_panel.refresh()
        self.refresh_status()
        self.update_window_title()

    def refresh_views(self) -> None:
        self.map_view.update()
        self.palette_panel.refresh()
        self.layer_panel.update_rows()
        self.status.update_all()

    def refresh_status(self) -> None:
        self.hover_tile_text = f"{self.hover_tile.x()}, {self.hover_tile.y()}" if self.hover_tile is not None else "-"
        self.hover_pixel_text = f"{self.hover_pixel[0]}, {self.hover_pixel[1]}" if self.hover_pixel is not None else "-"
        self.status.update_all()

    def update_window_title(self) -> None:
        name = Path(self.current_file).name if self.current_file else "Untitled.world"
        modified = " *" if self.modified else ""
        self.setWindowTitle(f"Tilemap Editor - {name}{modified}")

    def active_layer(self) -> Optional[TileLayer]:
        if 0 <= self.active_layer_index < len(self.map.layers):
            return self.map.layers[self.active_layer_index]
        return None

    def active_layer_name(self) -> str:
        layer = self.active_layer()
        return layer.name if layer else "-"

    def set_modified(self, value: bool = True) -> None:
        self.modified = value
        self.update_window_title()

    # -- palette / brush ------------------------------------------------------------

    def brush_stamp_available(self) -> bool:
        return bool(self.current_stamp_matrix())

    def current_stamp_matrix(self) -> list[list[TileRef]]:
        if self.brush_selection:
            return [row[:] for row in self.brush_selection]
        if self.palette_selection.is_valid() and self.palette_selection_letter in self.tileset_library.sets:
            return self.extract_tileset_matrix(self.palette_selection_letter, self.palette_selection)
        if not self.selected_ref.is_empty():
            return [[self.selected_ref]]
        return []

    def extract_tileset_matrix(self, letter: str, region: SelectionRegion) -> list[list[TileRef]]:
        tileset = self.tileset_library.sets.get(letter)
        if tileset is None or not region.is_valid():
            return []
        matrix: list[list[TileRef]] = []
        for y in range(region.y, region.y + region.height):
            row = []
            for x in range(region.x, region.x + region.width):
                index = y * tileset.columns + x
                row.append(TileRef(letter, index) if 0 <= index < tileset.count() else EMPTY_TILE)
            matrix.append(row)
        return matrix

    def set_active_tileset_letter(self, letter: str, refresh: bool = True) -> None:
        if letter == self.active_tileset_letter:
            return
        self.active_tileset_letter = letter
        if refresh:
            index = self.tileset_library.letters().index(letter) if letter in self.tileset_library.sets else -1
            if index >= 0:
                self.palette_panel.tabs.setCurrentIndex(index)

    def select_single_tile(self, letter: str, tx: int, ty: int) -> None:
        tileset = self.tileset_library.sets.get(letter)
        if tileset is None:
            return
        self.palette_selection = SelectionRegion(tx, ty, 1, 1)
        self.palette_selection_letter = letter
        index = ty * tileset.columns + tx
        self.selected_ref = TileRef(letter, index) if 0 <= index < tileset.count() else EMPTY_TILE
        self.brush_selection = [[self.selected_ref]] if not self.selected_ref.is_empty() else []
        self.refresh_views()

    def set_palette_selection_region(self, letter: str, x0: int, y0: int, x1: int, y1: int) -> None:
        tileset = self.tileset_library.sets.get(letter)
        if tileset is None:
            return
        x1 = max(0, min(x1, tileset.columns - 1))
        y1 = max(0, min(y1, tileset.rows - 1))
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        self.palette_selection = SelectionRegion(x0, y0, x1 - x0 + 1, y1 - y0 + 1)
        self.palette_selection_letter = letter
        index = y0 * tileset.columns + x0
        self.selected_ref = TileRef(letter, index) if 0 <= index < tileset.count() else EMPTY_TILE
        self.refresh_views()

    def commit_palette_stamp_selection(self) -> None:
        # Extract straight from the region that was just dragged, rather than going
        # through current_stamp_matrix() (which would just return the *previous*
        # brush_selection, since that function checks brush_selection first).
        self.brush_selection = self.extract_tileset_matrix(self.palette_selection_letter, self.palette_selection)
        self.palette_panel.update_previews()

    def select_current_tile_from_map(self, ref: TileRef) -> None:
        self.selected_ref = ref
        self.palette_selection = SelectionRegion(0, 0, 0, 0)
        if not ref.is_empty() and ref.letter in self.tileset_library.sets:
            self.set_active_tileset_letter(ref.letter)
        self.refresh_views()

    def set_tool(self, tool: Tool) -> None:
        self.current_tool = tool
        for action, t in [(self.act_single, Tool.SINGLE), (self.act_rect, Tool.RECTANGLE), (self.act_fill, Tool.FILL), (self.act_eyedropper, Tool.EYEDROPPER), (self.act_erase, Tool.ERASE), (self.act_selection, Tool.SELECTION)]:
            action.setChecked(t == tool)
        self.refresh_status()
        self.refresh_views()

    def change_palette_zoom(self, direction: int) -> None:
        self.palette_zoom = max(1, min(8, self.palette_zoom + (1 if direction > 0 else -1)))
        self.palette_panel.refresh()

    def toggle_grid(self) -> None:
        self.grid_visible = self.act_grid.isChecked()
        self.refresh_views()

    def toggle_checkerboard(self) -> None:
        self.checkerboard_background = self.act_checkerboard.isChecked()
        self.refresh_views()

    def pick_background_color(self) -> None:
        color = QColorDialog.getColor(self.background_color, self, "Background Color")
        if color.isValid():
            self.background_color = color
            self.refresh_views()

    def pick_grid_color(self) -> None:
        color = QColorDialog.getColor(self.grid_color, self, "Grid Color")
        if color.isValid():
            self.grid_color = color
            self.refresh_views()

    def zoom_at_cursor(self, pos: QPointF, direction: int) -> None:
        before = self.map_view.view_to_world(pos.x(), pos.y())
        self.camera.set_zoom_index(self.camera.zoom_index + (1 if direction > 0 else -1))
        new_zoom = self.camera.zoom
        self.camera.x = max(0.0, before.x() - pos.x() / new_zoom)
        self.camera.y = max(0.0, before.y() - pos.y() / new_zoom)
        self.refresh_views()

    def zoom_in(self) -> None:
        self.camera.set_zoom_index(self.camera.zoom_index + 1)
        self.refresh_views()

    def zoom_out(self) -> None:
        self.camera.set_zoom_index(self.camera.zoom_index - 1)
        self.refresh_views()

    def reset_zoom(self) -> None:
        self.camera.set_zoom_to_factor(1.0)
        self.camera.x = 0.0
        self.camera.y = 0.0
        self.refresh_views()

    def map_viewport_update_from_region(self, region: SelectionRegion) -> None:
        if not region.is_valid():
            self.map_view.update()
            return
        tw, th = self.map.tile_w, self.map.tile_h
        zoom = self.camera.zoom
        rect = QRect(int((region.x * tw - self.camera.x) * zoom) - 4, int((region.y * th - self.camera.y) * zoom) - 4, int(region.width * tw * zoom) + 8, int(region.height * th * zoom) + 8)
        self.map_view.update(rect)

    # -- painting --------------------------------------------------------------------

    def paint_cell(self, x: int, y: int, ref: TileRef, change_list: Optional[list[StrokeChange]] = None, seen: Optional[set[int]] = None) -> None:
        layer = self.active_layer()
        if layer is None or layer.locked or not layer.visible or not layer.in_bounds(x, y):
            return
        idx = layer.index(x, y)
        if seen is not None and idx in seen:
            return
        old_ref = layer.get_by_index(idx)
        if old_ref == ref:
            return
        layer.set_by_index(idx, ref)
        if change_list is not None and seen is not None:
            change_list.append(StrokeChange(self.active_layer_index, idx, old_ref, ref))
            seen.add(idx)
        self.map_viewport_update_from_region(SelectionRegion(x, y, 1, 1))
        self.set_modified()

    def paint_current_brush_at(self, x: int, y: int, change_list: Optional[list[StrokeChange]] = None, seen: Optional[set[int]] = None) -> None:
        stamp = self.current_stamp_matrix()
        if not stamp:
            return
        if len(stamp) == 1 and len(stamp[0]) == 1:
            self.paint_cell(x, y, stamp[0][0], change_list, seen)
            return
        for yy, row in enumerate(stamp):
            for xx, ref in enumerate(row):
                self.paint_cell(x + xx, y + yy, ref, change_list, seen)

    def erase_cell(self, x: int, y: int, record_undo: bool = False) -> None:
        layer = self.active_layer()
        if layer is None or layer.locked or not layer.visible or not layer.in_bounds(x, y):
            return
        idx = layer.index(x, y)
        old_ref = layer.get_by_index(idx)
        if old_ref.is_empty():
            return
        layer.set_by_index(idx, EMPTY_TILE)
        if record_undo:
            def undo_one() -> None:
                layer.set_by_index(idx, old_ref)
            def redo_one() -> None:
                layer.set_by_index(idx, EMPTY_TILE)
            self.undo_manager.push(UndoAction("Erase", undo_one, redo_one))
        self.map_viewport_update_from_region(SelectionRegion(x, y, 1, 1))
        self.set_modified()

    def _apply_stroke_changes(self, changes: list[StrokeChange], use_new: bool) -> None:
        for c in changes:
            if 0 <= c.layer_index < len(self.map.layers):
                self.map.layers[c.layer_index].set_by_index(c.index, c.new_ref if use_new else c.old_ref)

    def commit_stroke(self, changes: list[StrokeChange], description: str) -> None:
        if not changes:
            return
        snapshot = [StrokeChange(c.layer_index, c.index, c.old_ref, c.new_ref) for c in changes]
        self.undo_manager.push(UndoAction(
            description,
            lambda: self._apply_stroke_changes(snapshot, use_new=False),
            lambda: self._apply_stroke_changes(snapshot, use_new=True),
        ))
        self.set_modified()
        self.refresh_all()

    def commit_rectangle_stamp(self, region: SelectionRegion) -> None:
        if not region.is_valid() or not self.brush_stamp_available():
            return
        matrix = nine_slice_matrix(self.current_stamp_matrix(), region.width, region.height)
        if not matrix:
            return
        changes: list[StrokeChange] = []
        seen: set[int] = set()
        for yy, row in enumerate(matrix):
            for xx, ref in enumerate(row):
                self.paint_cell(region.x + xx, region.y + yy, ref, changes, seen)
        if not changes:
            return
        self.commit_stroke(changes, "Rectangle Brush")

    def flood_fill(self, x: int, y: int) -> None:
        layer = self.active_layer()
        if layer is None or layer.locked or not layer.visible or not layer.in_bounds(x, y):
            return
        target_ref = layer.get(x, y)
        stamp = self.current_stamp_matrix()
        new_ref = stamp[0][0] if stamp else EMPTY_TILE
        if target_ref == new_ref:
            return
        q = deque([(x, y)])
        visited: set[tuple[int, int]] = set()
        changes: list[StrokeChange] = []
        while q:
            cx, cy = q.popleft()
            if (cx, cy) in visited or not layer.in_bounds(cx, cy):
                continue
            visited.add((cx, cy))
            if layer.get(cx, cy) != target_ref:
                continue
            idx = layer.index(cx, cy)
            changes.append(StrokeChange(self.active_layer_index, idx, target_ref, new_ref))
            layer.set_by_index(idx, new_ref)
            q.extend([(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)])
        if not changes:
            return
        self.commit_stroke(changes, "Fill")

    def pick_from_map(self, x: int, y: int) -> None:
        layer = self.active_layer()
        if layer is None or not layer.in_bounds(x, y):
            return
        self.select_current_tile_from_map(layer.get(x, y))

    def commit_region_clear(self, region: SelectionRegion) -> None:
        if not region.is_valid():
            return
        layer = self.active_layer()
        if layer is None or layer.locked or not layer.visible:
            return
        changes: list[StrokeChange] = []
        for yy in range(region.y, min(self.map.height, region.y + region.height)):
            for xx in range(region.x, min(self.map.width, region.x + region.width)):
                idx = layer.index(xx, yy)
                old_ref = layer.get_by_index(idx)
                if old_ref.is_empty():
                    continue
                layer.set_by_index(idx, EMPTY_TILE)
                changes.append(StrokeChange(self.active_layer_index, idx, old_ref, EMPTY_TILE))
        if not changes:
            return
        self.commit_stroke(changes, "Clear Region")

    def delete_selection(self) -> None:
        if self.map_selection.is_valid():
            self.commit_region_clear(self.map_selection)
            self.map_selection = SelectionRegion()
            return
        if self.hover_tile is not None:
            self.erase_cell(self.hover_tile.x(), self.hover_tile.y(), record_undo=True)

    def clear_map_selection(self) -> None:
        self.map_selection = SelectionRegion()
        self.refresh_views()

    # -- layers ------------------------------------------------------------------

    def capture_layers_state(self) -> dict[str, Any]:
        return {"layers": [layer.clone() for layer in self.map.layers], "active": self.active_layer_index}

    def restore_layers_state(self, snapshot: dict[str, Any]) -> None:
        self.map.layers = [layer.clone() for layer in snapshot["layers"]]
        if not self.map.layers:
            self.map.layers = [TileLayer(self.map.width, self.map.height)]
        self.active_layer_index = max(0, min(int(snapshot.get("active", 0)), len(self.map.layers) - 1))
        self.layer_panel.refresh()
        self.refresh_all()

    def push_layers_undo(self, before: dict[str, Any], after: dict[str, Any], description: str) -> None:
        self.undo_manager.push(UndoAction(description, lambda: self.restore_layers_state(before), lambda: self.restore_layers_state(after)))
        self.set_modified()

    def set_active_layer(self, index: int) -> None:
        if 0 <= index < len(self.map.layers):
            self.active_layer_index = index
            self.layer_panel.update_rows()
            self.refresh_status()
            self.refresh_views()

    def set_layer_visibility(self, index: int, visible: bool) -> None:
        if not (0 <= index < len(self.map.layers)):
            return
        before = self.capture_layers_state()
        self.map.layers[index].visible = visible
        self.push_layers_undo(before, self.capture_layers_state(), "Layer Visibility")
        self.refresh_all()

    def set_layer_locked(self, index: int, locked: bool) -> None:
        if not (0 <= index < len(self.map.layers)):
            return
        before = self.capture_layers_state()
        self.map.layers[index].locked = locked
        self.push_layers_undo(before, self.capture_layers_state(), "Layer Lock")
        self.refresh_all()

    def add_layer(self) -> None:
        before = self.capture_layers_state()
        self.map.layers.append(TileLayer(self.map.width, self.map.height, f"Layer {len(self.map.layers) + 1}"))
        self.active_layer_index = len(self.map.layers) - 1
        self.push_layers_undo(before, self.capture_layers_state(), "Add Layer")
        self.refresh_all()

    def duplicate_current_layer(self) -> None:
        layer = self.active_layer()
        if layer is None:
            return
        before = self.capture_layers_state()
        new_layer = layer.clone()
        new_layer.name = f"{layer.name} Copy"
        self.map.layers.insert(self.active_layer_index + 1, new_layer)
        self.active_layer_index += 1
        self.push_layers_undo(before, self.capture_layers_state(), "Duplicate Layer")
        self.refresh_all()

    def delete_current_layer(self) -> None:
        if len(self.map.layers) <= 1:
            QMessageBox.information(self, "Delete Layer", "A map must have at least one layer.")
            return
        before = self.capture_layers_state()
        del self.map.layers[self.active_layer_index]
        self.active_layer_index = max(0, min(self.active_layer_index, len(self.map.layers) - 1))
        self.push_layers_undo(before, self.capture_layers_state(), "Delete Layer")
        self.refresh_all()

    def move_layer(self, direction: int) -> None:
        new_index = self.active_layer_index + direction
        if not (0 <= self.active_layer_index < len(self.map.layers)) or not (0 <= new_index < len(self.map.layers)):
            return
        before = self.capture_layers_state()
        self.map.layers[self.active_layer_index], self.map.layers[new_index] = self.map.layers[new_index], self.map.layers[self.active_layer_index]
        self.active_layer_index = new_index
        self.push_layers_undo(before, self.capture_layers_state(), "Move Layer")
        self.refresh_all()

    def rename_current_layer(self) -> None:
        layer = self.active_layer()
        if layer is None:
            return
        text, ok = QInputDialog.getText(self, "Rename Layer", "Layer Name:", text=layer.name)
        if not ok or not text.strip():
            return
        before = self.capture_layers_state()
        layer.name = text.strip()
        self.push_layers_undo(before, self.capture_layers_state(), "Rename Layer")
        self.refresh_all()

    def undo(self) -> None:
        if self.undo_manager.can_undo():
            self.undo_manager.undo()
            self.refresh_all()
            self.set_modified(True)

    def redo(self) -> None:
        if self.undo_manager.can_redo():
            self.undo_manager.redo()
            self.refresh_all()
            self.set_modified(True)

    # -- tileset / file management -------------------------------------------------

    def load_tileset_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Load Tileset Folder", self.tileset_library.directory or "")
        if not directory:
            return
        default_w = self.tileset_library.tile_w if self.tileset_library.is_loaded() else self.map.tile_w
        default_h = self.tileset_library.tile_h if self.tileset_library.is_loaded() else self.map.tile_h
        tile_w, ok = QInputDialog.getInt(self, "Tileset Tile Width", "Tile width (px):", value=default_w, min=1, max=100000)
        if not ok:
            return
        tile_h, ok = QInputDialog.getInt(self, "Tileset Tile Height", "Tile height (px):", value=default_h, min=1, max=100000)
        if not ok:
            return
        before = self.tileset_library.snapshot()
        try:
            failed, unreferenceable = self.tileset_library.load_directory(directory, tile_w, tile_h)
        except Exception as exc:
            QMessageBox.critical(self, "Load Tileset Folder", str(exc))
            return
        after = self.tileset_library.snapshot()
        self.undo_manager.push(UndoAction("Load Tileset Folder", lambda: self.tileset_library.restore(before), lambda: self.tileset_library.restore(after)))
        letters = self.tileset_library.letters()
        self.active_tileset_letter = letters[0] if letters else ""
        self.selected_ref = EMPTY_TILE
        self.brush_selection = []
        self.palette_selection = SelectionRegion()
        self.set_modified()
        self.palette_panel.rebuild_tabs()
        self.refresh_all()
        if failed:
            QMessageBox.warning(self, "Some tilesets skipped", "These PNGs couldn't be sliced at that tile size:\n" + "\n".join(failed))
        if unreferenceable:
            QMessageBox.warning(
                self,
                "Unusable tileset names",
                "These tilesets loaded, but their filenames mix letters and digits, so no .world "
                "token can ever address them (rename to letters only, e.g. 'A.png'):\n" + "\n".join(unreferenceable),
            )

    def change_tile_size(self) -> None:
        if not self.tileset_library.is_loaded():
            QMessageBox.information(self, "Change Tile Size", "Load a tileset folder first.")
            return
        tile_w, ok = QInputDialog.getInt(self, "Change Tile Width", "Tile width (px):", value=self.tileset_library.tile_w, min=1, max=100000)
        if not ok:
            return
        tile_h, ok = QInputDialog.getInt(self, "Change Tile Height", "Tile height (px):", value=self.tileset_library.tile_h, min=1, max=100000)
        if not ok:
            return
        before = self.tileset_library.snapshot()
        try:
            self.tileset_library.load_directory(self.tileset_library.directory, tile_w, tile_h)
        except Exception as exc:
            QMessageBox.critical(self, "Change Tile Size Failed", str(exc))
            self.tileset_library.restore(before)
            return
        after = self.tileset_library.snapshot()
        self.undo_manager.push(UndoAction("Tileset Tile Size", lambda: self.tileset_library.restore(before), lambda: self.tileset_library.restore(after)))
        self.map.tile_w = tile_w
        self.map.tile_h = tile_h
        self.set_modified()
        self.palette_panel.rebuild_tabs()
        self.refresh_all()

    def new_map(self) -> None:
        if not self.maybe_save_current():
            return
        dlg = NewMapDialog(self, {"world_w": self.map.width, "world_h": self.map.height, "tile_w": self.map.tile_w, "tile_h": self.map.tile_h, "layers": len(self.map.layers)})
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        width, height, tile_w, tile_h, num_layers = dlg.values()
        self.map = TileMap(width, height, tile_w, tile_h, layers=[TileLayer(width, height, f"Layer {i + 1}") for i in range(num_layers)])
        self.camera = Camera()
        self.undo_manager.clear()
        self.current_file = ""
        self.selected_ref = EMPTY_TILE
        self.brush_selection = []
        self.palette_selection = SelectionRegion()
        self.map_selection = SelectionRegion()
        self.active_layer_index = 0
        self.modified = False
        self.refresh_all()

    def open_map(self) -> None:
        if not self.maybe_save_current():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Map", "", "World Files (*.world)")
        if not path:
            return
        self.load_map_from_path(path)

    def save_map(self) -> None:
        if not self.current_file:
            self.save_map_as()
            return
        self.save_to_path(self.current_file)

    def save_map_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Map As", self.current_file or "untitled.world", "World Files (*.world)")
        if not path:
            return
        if not path.lower().endswith(".world"):
            path += ".world"
        self.save_to_path(path)

    def editor_state_dict(self) -> dict[str, Any]:
        return {
            "camera": {"x": self.camera.x, "y": self.camera.y, "zoomIndex": self.camera.zoom_index},
            "grid": {"visible": self.grid_visible, "color": self.grid_color.name()},
            "backgroundColor": self.background_color.name(),
            "checkerboard": self.checkerboard_background,
            "tool": self.current_tool.value,
            "activeLayer": self.active_layer_index,
            "tilesetDirectory": self.tileset_library.directory,
            "tileW": self.tileset_library.tile_w,
            "tileH": self.tileset_library.tile_h,
        }

    def apply_editor_state_dict(self, data: dict[str, Any]) -> None:
        camera_data = data.get("camera", {})
        if isinstance(camera_data, dict):
            self.camera.x = float(camera_data.get("x", 0.0))
            self.camera.y = float(camera_data.get("y", 0.0))
            self.camera.set_zoom_index(int(camera_data.get("zoomIndex", 2)))
        grid_data = data.get("grid", {})
        if isinstance(grid_data, dict):
            self.grid_visible = bool(grid_data.get("visible", True))
            color = QColor(str(grid_data.get("color", "#505050")))
            self.grid_color = color if color.isValid() else QColor(80, 80, 80)
        bg = QColor(str(data.get("backgroundColor", "#1e1e1e")))
        self.background_color = bg if bg.isValid() else QColor(30, 30, 30)
        self.checkerboard_background = bool(data.get("checkerboard", True))
        tool_value = data.get("tool", Tool.SINGLE.value)
        self.current_tool = Tool(tool_value) if tool_value in Tool._value2member_map_ else Tool.SINGLE
        self.active_layer_index = max(0, min(int(data.get("activeLayer", 0)), len(self.map.layers) - 1))
        directory = data.get("tilesetDirectory", "")
        if directory and os.path.isdir(directory):
            try:
                self.tileset_library.load_directory(directory, int(data.get("tileW", self.map.tile_w)), int(data.get("tileH", self.map.tile_h)))
            except Exception:
                self.tileset_library.clear()

    def save_to_path(self, path: str) -> None:
        try:
            WorldFileIO.write(path, self.map)
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", f"Could not save map.\n\n{exc}")
            return
        FileManager.save_sidecar(path, self.editor_state_dict())
        self.current_file = path
        self.set_modified(False)
        FileManager.save_recent(self.settings, path)
        self.delete_recovery_file()
        self.refresh_recent_menu()
        self.refresh_status()
        self.update_window_title()

    def load_map_from_path(self, path: str) -> None:
        try:
            loaded_map = WorldFileIO.read(path)
        except Exception as exc:
            QMessageBox.critical(self, "Open Map Failed", f"Could not open map.\n\n{exc}")
            return
        self.map = loaded_map
        self.camera = Camera()
        self.current_file = path
        self.modified = False
        self.undo_manager.clear()
        self.selected_ref = EMPTY_TILE
        self.brush_selection = []
        self.palette_selection = SelectionRegion()
        self.map_selection = SelectionRegion()
        self.tileset_library.clear()
        sidecar = FileManager.load_sidecar(path)
        if sidecar:
            self.apply_editor_state_dict(sidecar)
        else:
            self.active_layer_index = 0
        self.palette_panel.rebuild_tabs()
        self.refresh_all()
        FileManager.save_recent(self.settings, path)
        self.refresh_recent_menu()
        self.update_window_title()

    def maybe_save_current(self) -> bool:
        if not self.modified:
            return True
        choice = QMessageBox.question(self, "Unsaved Changes", "The map has unsaved changes. Save now?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
        if choice == QMessageBox.StandardButton.Cancel:
            return False
        if choice == QMessageBox.StandardButton.Yes:
            self.save_map()
            return not self.modified
        self.modified = False
        return True

    def refresh_recent_menu(self) -> None:
        self.recent_menu.clear()
        recents = FileManager.recent_files(self.settings)
        if not recents:
            action = QAction("(None)", self)
            action.setEnabled(False)
            self.recent_menu.addAction(action)
            return
        for path in recents[:MAX_RECENTS]:
            action = QAction(path, self)
            action.triggered.connect(lambda checked=False, p=path: self.open_recent(p))
            self.recent_menu.addAction(action)

    def open_recent(self, path: str) -> None:
        if not self.maybe_save_current():
            return
        if Path(path).exists():
            self.load_map_from_path(path)
        else:
            QMessageBox.warning(self, "Recent File", f"File no longer exists:\n{path}")
            self.refresh_recent_menu()

    def add_recent_file(self, path: str) -> None:
        FileManager.save_recent(self.settings, path)
        self.refresh_recent_menu()

    # -- autosave / recovery -------------------------------------------------------

    def check_recovery(self) -> None:
        recovery = FileManager.recovery_path()
        if not recovery.exists():
            return
        choice = QMessageBox.question(self, "Recover Autosave", "A recovery file was found. Load it?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if choice == QMessageBox.StandardButton.Yes:
            try:
                loaded_map = WorldFileIO.read(str(recovery))
                self.map = loaded_map
                self.current_file = ""
                self.modified = True
                self.undo_manager.clear()
                meta_path = FileManager.recovery_meta_path()
                if meta_path.exists():
                    try:
                        with meta_path.open("r", encoding="utf-8") as f:
                            self.apply_editor_state_dict(json.load(f))
                    except Exception:
                        pass
                self.palette_panel.rebuild_tabs()
                self.refresh_all()
            except Exception as exc:
                QMessageBox.critical(self, "Recovery Failed", str(exc))
        else:
            try:
                recovery.unlink(missing_ok=True)
                FileManager.recovery_meta_path().unlink(missing_ok=True)
            except Exception:
                pass

    def autosave(self) -> None:
        if not self.modified:
            return
        try:
            WorldFileIO.write(str(FileManager.recovery_path()), self.map)
            with FileManager.recovery_meta_path().open("w", encoding="utf-8") as f:
                json.dump(self.editor_state_dict(), f)
        except Exception:
            return

    def delete_recovery_file(self) -> None:
        try:
            FileManager.recovery_path().unlink(missing_ok=True)
            FileManager.recovery_meta_path().unlink(missing_ok=True)
        except Exception:
            pass

    # -- Qt event overrides --------------------------------------------------------

    def closeEvent(self, event) -> None:
        if not self.maybe_save_current():
            event.ignore()
            return
        if self.modified:
            self.autosave()
        else:
            self.delete_recovery_file()
        event.accept()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        if not event.mimeData().hasUrls():
            return
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if not path:
                continue
            if os.path.isdir(path):
                if not self.maybe_save_current():
                    return
                default_w = self.tileset_library.tile_w if self.tileset_library.is_loaded() else self.map.tile_w
                default_h = self.tileset_library.tile_h if self.tileset_library.is_loaded() else self.map.tile_h
                tile_w, ok = QInputDialog.getInt(self, "Tileset Tile Width", "Tile width (px):", value=default_w, min=1, max=100000)
                if not ok:
                    continue
                tile_h, ok = QInputDialog.getInt(self, "Tileset Tile Height", "Tile height (px):", value=default_h, min=1, max=100000)
                if not ok:
                    continue
                try:
                    self.tileset_library.load_directory(path, tile_w, tile_h)
                    self.set_modified()
                    self.palette_panel.rebuild_tabs()
                    self.refresh_all()
                except Exception as exc:
                    QMessageBox.critical(self, "Load Tileset Folder", str(exc))
            elif path.lower().endswith(".world"):
                if not self.maybe_save_current():
                    return
                self.load_map_from_path(path)
                self.add_recent_file(path)
        event.acceptProposedAction()

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.StandardKey.New):
            self.new_map()
            return
        if event.matches(QKeySequence.StandardKey.Open):
            self.open_map()
            return
        if event.matches(QKeySequence.StandardKey.Save):
            self.save_map()
            return
        if event.matches(QKeySequence.StandardKey.Undo):
            self.undo()
            return
        if event.matches(QKeySequence.StandardKey.Redo):
            self.redo()
            return
        key = event.key()
        if key == Qt.Key.Key_Delete:
            self.delete_selection()
            return
        if key == Qt.Key.Key_Space:
            return
        # Tool shortcuts (I/R/F/E/B/S) and Ctrl+G-style toggles are owned by the
        # QActions built in _build_actions/_build_menus, so they aren't duplicated
        # here (the previous version of this file had a second, mismatched copy of
        # this mapping in keyPressEvent that disagreed with the action shortcuts).
        super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.refresh_status()


def apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = app.palette()
    pal.setColor(pal.ColorRole.Window, QColor(37, 37, 38))
    pal.setColor(pal.ColorRole.WindowText, QColor(230, 230, 230))
    pal.setColor(pal.ColorRole.Base, QColor(28, 28, 29))
    pal.setColor(pal.ColorRole.AlternateBase, QColor(45, 45, 46))
    pal.setColor(pal.ColorRole.ToolTipBase, QColor(255, 255, 255))
    pal.setColor(pal.ColorRole.ToolTipText, QColor(0, 0, 0))
    pal.setColor(pal.ColorRole.Text, QColor(230, 230, 230))
    pal.setColor(pal.ColorRole.Button, QColor(48, 48, 50))
    pal.setColor(pal.ColorRole.ButtonText, QColor(230, 230, 230))
    pal.setColor(pal.ColorRole.Highlight, QColor(90, 130, 180))
    pal.setColor(pal.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(pal)


def main() -> None:
    app = QApplication(sys.argv)
    QApplication.setOrganizationName(APP_ORG)
    QApplication.setApplicationName(APP_NAME)
    apply_dark_theme(app)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise