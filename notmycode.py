from __future__ import annotations

import json
import math
import os
import sys
import traceback
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

try:
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
        QColor,
        QCursor,
        QFont,
        QIcon,
        QImage,
        QKeySequence,
        QPainter,
        QPen,
        QPixmap,
        QTransform,
    )
    from PySide6.QtWidgets import (
        QApplication,
        QAbstractScrollArea,
        QButtonGroup,
        QColorDialog,
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QGraphicsOpacityEffect,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMenu,
        QMenuBar,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSlider,
        QSizePolicy,
        QSpinBox,
        QStatusBar,
        QStyle,
        QToolBar,
        QToolButton,
        QVBoxLayout,
        QWidget,
        QCheckBox,
        QSplitter,
    )
except ImportError:  # pragma: no cover
    from PyQt6.QtCore import (
        QSettings,
        QStandardPaths,
        QTimer,
        Qt,
        QRect,
        QRectF,
        QSize,
        QPoint,
        QPointF,
        pyqtSignal as Signal,
    )
    from PyQt6.QtGui import (
        QAction,
        QColor,
        QCursor,
        QFont,
        QIcon,
        QImage,
        QKeySequence,
        QPainter,
        QPen,
        QPixmap,
        QTransform,
    )
    from PyQt6.QtWidgets import (
        QApplication,
        QAbstractScrollArea,
        QButtonGroup,
        QColorDialog,
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QGraphicsOpacityEffect,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMenu,
        QMenuBar,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSlider,
        QSizePolicy,
        QSpinBox,
        QStatusBar,
        QStyle,
        QToolBar,
        QToolButton,
        QVBoxLayout,
        QWidget,
        QCheckBox,
        QSplitter,
    )


APP_ORG = "OpenAI"
APP_NAME = "TilemapEditor"
RECOVERY_FILE = "autosave_recovery.json"
MAX_RECENTS = 10
ZOOM_LEVELS = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0]
DEFAULT_TILE_SIZE = 8


class Tool(Enum):
    SINGLE = "single"
    RECTANGLE = "rectangle"
    ERASE = "erase"
    FILL = "fill"
    EYEDROPPER = "eyedropper"
    SELECTION = "selection"


@dataclass
class TileTransform:
    """Placement transform stored separately from tile ID."""

    hflip: bool = False
    vflip: bool = False
    rotation: int = 0  # 0..3, clockwise quarter turns

    def normalized(self) -> "TileTransform":
        return TileTransform(self.hflip, self.vflip, self.rotation % 4)

    def encode(self) -> int:
        r = self.rotation % 4
        return (r << 2) | (1 if self.hflip else 0) | (2 if self.vflip else 0)

    @staticmethod
    def decode(flags: int) -> "TileTransform":
        return TileTransform(bool(flags & 1), bool(flags & 2), (flags >> 2) & 3)

    def to_dict(self) -> dict[str, Any]:
        return {"hflip": self.hflip, "vflip": self.vflip, "rotation": self.rotation % 4}

    @staticmethod
    def from_dict(data: Any) -> "TileTransform":
        if not isinstance(data, dict):
            return TileTransform()
        return TileTransform(bool(data.get("hflip", False)), bool(data.get("vflip", False)), int(data.get("rotation", 0)) % 4)


@dataclass
class SelectionRegion:
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    def is_valid(self) -> bool:
        return self.width > 0 and self.height > 0

    def normalized(self) -> "SelectionRegion":
        return SelectionRegion(self.x, self.y, self.width, self.height)

    def contains(self, tx: int, ty: int) -> bool:
        return self.is_valid() and self.x <= tx < self.x + self.width and self.y <= ty < self.y + self.height

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
        self.limit = max(100, limit)
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
    """Single layer of integer tile IDs plus transform flags."""

    def __init__(self, width: int, height: int, name: str = "Layer 1", visible: bool = True, locked: bool = False, opacity: float = 1.0) -> None:
        self.name = name
        self.visible = visible
        self.locked = locked
        self.opacity = float(opacity)
        self.width = int(width)
        self.height = int(height)
        total = max(0, self.width * self.height)
        self.tile_ids: list[int] = [0] * total
        self.transforms: list[int] = [0] * total

    def index(self, x: int, y: int) -> int:
        return y * self.width + x

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def get(self, x: int, y: int) -> tuple[int, TileTransform]:
        idx = self.index(x, y)
        return self.tile_ids[idx], TileTransform.decode(self.transforms[idx])

    def get_by_index(self, idx: int) -> tuple[int, TileTransform]:
        return self.tile_ids[idx], TileTransform.decode(self.transforms[idx])

    def set_cell(self, x: int, y: int, tile_id: int, transform: Optional[TileTransform] = None) -> tuple[int, int]:
        idx = self.index(x, y)
        old = self.tile_ids[idx], self.transforms[idx]
        self.tile_ids[idx] = max(0, int(tile_id))
        self.transforms[idx] = (transform or TileTransform()).encode() if tile_id else 0
        return old

    def set_by_index(self, idx: int, tile_id: int, transform_flags: int = 0) -> tuple[int, int]:
        old = self.tile_ids[idx], self.transforms[idx]
        self.tile_ids[idx] = max(0, int(tile_id))
        self.transforms[idx] = transform_flags if tile_id else 0
        return old

    def clear(self) -> None:
        self.tile_ids[:] = [0] * (self.width * self.height)
        self.transforms[:] = [0] * (self.width * self.height)

    def clone(self) -> "TileLayer":
        layer = TileLayer(self.width, self.height, self.name, self.visible, self.locked, self.opacity)
        layer.tile_ids = self.tile_ids.copy()
        layer.transforms = self.transforms.copy()
        return layer

    def to_dict(self) -> dict[str, Any]:
        tiles_2d = [self.tile_ids[y * self.width:(y + 1) * self.width] for y in range(self.height)]
        transforms_2d = [self.transforms[y * self.width:(y + 1) * self.width] for y in range(self.height)]
        return {
            "name": self.name,
            "visible": self.visible,
            "locked": self.locked,
            "opacity": self.opacity,
            "tiles": tiles_2d,
            "transforms": transforms_2d,
        }

    @staticmethod
    def from_dict(data: Any, width: int, height: int) -> "TileLayer":
        if not isinstance(data, dict):
            return TileLayer(width, height)
        layer = TileLayer(width, height, str(data.get("name", "Layer")), bool(data.get("visible", True)), bool(data.get("locked", False)), float(data.get("opacity", 1.0)))
        tiles = data.get("tiles", [])
        transforms = data.get("transforms", [])
        if isinstance(tiles, list):
            for y in range(min(height, len(tiles))):
                row = tiles[y] if isinstance(tiles[y], list) else []
                trow = transforms[y] if isinstance(transforms, list) and y < len(transforms) and isinstance(transforms[y], list) else []
                for x in range(min(width, len(row))):
                    idx = layer.index(x, y)
                    try:
                        value = int(row[x])
                    except Exception:
                        value = 0
                    layer.tile_ids[idx] = max(0, value)
                    try:
                        layer.transforms[idx] = int(trow[x]) if x < len(trow) else 0
                    except Exception:
                        layer.transforms[idx] = 0
        return layer


class TileMap:
    def __init__(self, width: int, height: int, tile_size: int, layers: Optional[list[TileLayer]] = None) -> None:
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.tile_size = max(1, int(tile_size))
        self.layers = layers if layers is not None else [TileLayer(self.width, self.height, "Layer 1")]
        self.tileset_path: str = ""

    def create_default_layer(self) -> None:
        self.layers = [TileLayer(self.width, self.height, "Layer 1")]

    def to_dict(self, editor_state: dict[str, Any]) -> dict[str, Any]:
        return {
            "mapWidth": self.width,
            "mapHeight": self.height,
            "tileSize": self.tile_size,
            "tilesetPath": self.tileset_path,
            "camera": editor_state.get("camera", {}),
            "grid": editor_state.get("grid", {}),
            "editor": editor_state.get("editor", {}),
            "layers": [layer.to_dict() for layer in self.layers],
        }

    @staticmethod
    def from_dict(data: Any) -> tuple["TileMap", dict[str, Any]]:
        if not isinstance(data, dict):
            raise ValueError("Invalid map JSON: root object must be a JSON object.")
        width = int(data.get("mapWidth", data.get("width", 1)))
        height = int(data.get("mapHeight", data.get("height", 1)))
        tile_size = int(data.get("tileSize", DEFAULT_TILE_SIZE))
        if width <= 0 or height <= 0 or tile_size <= 0:
            raise ValueError("Invalid map dimensions or tile size.")
        layers_data = data.get("layers", [])
        layers: list[TileLayer] = []
        if isinstance(layers_data, list) and layers_data:
            for layer_data in layers_data:
                layers.append(TileLayer.from_dict(layer_data, width, height))
        else:
            layers = [TileLayer(width, height, "Layer 1")]
        m = TileMap(width, height, tile_size, layers)
        m.tileset_path = str(data.get("tilesetPath", data.get("tileset", "")))
        return m, data


class TileSetModel:
    def __init__(self) -> None:
        self.path: str = ""
        self.tile_size: int = DEFAULT_TILE_SIZE
        self.image: Optional[QImage] = None
        self.tiles: list[QImage] = []
        self.columns: int = 0
        self.rows: int = 0
        self._cache: dict[tuple[int, int], QImage] = {}

    def is_loaded(self) -> bool:
        return self.image is not None and not self.image.isNull() and bool(self.tiles)

    def clear(self) -> None:
        self.path = ""
        self.image = None
        self.tiles.clear()
        self.columns = 0
        self.rows = 0
        self._cache.clear()

    def snapshot(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "tile_size": self.tile_size,
            "image": self.image.copy() if self.image and not self.image.isNull() else None,
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        image = snapshot.get("image")
        path = str(snapshot.get("path", ""))
        tile_size = int(snapshot.get("tile_size", DEFAULT_TILE_SIZE))
        if isinstance(image, QImage) and not image.isNull():
            self.load_from_image(image.copy(), path, tile_size)
        else:
            self.clear()
            self.path = path
            self.tile_size = tile_size

    def load(self, path: str, tile_size: int) -> None:
        image = QImage(path)
        if image.isNull():
            raise ValueError(f"Could not load PNG tileset: {path}")
        self.load_from_image(image, path, tile_size)

    def load_from_image(self, image: QImage, path: str, tile_size: int) -> None:
        if tile_size <= 0:
            raise ValueError("Tile size must be a positive integer.")
        if image.width() < tile_size or image.height() < tile_size:
            raise ValueError("Tileset image is smaller than the tile size.")
        self.path = path
        self.tile_size = int(tile_size)
        self.image = image.copy()
        self.columns = self.image.width() // self.tile_size
        self.rows = self.image.height() // self.tile_size
        if self.columns <= 0 or self.rows <= 0:
            raise ValueError("Tileset slicing produced no tiles.")
        self.tiles = []
        for y in range(self.rows):
            for x in range(self.columns):
                self.tiles.append(self.image.copy(x * self.tile_size, y * self.tile_size, self.tile_size, self.tile_size))
        self._cache.clear()

    def count(self) -> int:
        return len(self.tiles)

    def tile_image(self, tile_id: int) -> Optional[QImage]:
        if tile_id <= 0 or tile_id > len(self.tiles):
            return None
        return self.tiles[tile_id - 1]

    def transformed_tile(self, tile_id: int, transform_flags: int) -> Optional[QImage]:
        if tile_id <= 0:
            return None
        key = (tile_id, transform_flags)
        if key in self._cache:
            return self._cache[key]
        img = self.tile_image(tile_id)
        if img is None:
            return None
        transform = TileTransform.decode(transform_flags)
        transformed = img.mirrored(transform.hflip, transform.vflip)
        if transform.rotation % 4:
            qt = QTransform()
            qt.rotate(90 * (transform.rotation % 4))
            transformed = transformed.transformed(qt, Qt.TransformationMode.SmoothTransformation)
        self._cache[key] = transformed
        return transformed


@dataclass
class StrokeChange:
    layer_index: int
    index: int
    old_tile: int
    old_transform: int
    new_tile: int
    new_transform: int


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
    def save_json(path: str, data: dict[str, Any]) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def load_json(path: str) -> dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("JSON root must be an object.")
        return data

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


class ExportManager:
    @staticmethod
    def export_runtime_json(editor: "MainWindow", path: str) -> None:
        layers = []
        for layer in editor.map.layers:
            tiles_2d = [layer.tile_ids[y * layer.width:(y + 1) * layer.width] for y in range(layer.height)]
            layers.append({
                "name": layer.name,
                "visible": layer.visible,
                "locked": layer.locked,
                "opacity": layer.opacity,
                "tiles": tiles_2d,
            })
        data = {
            "tileSize": editor.map.tile_size,
            "mapWidth": editor.map.width,
            "mapHeight": editor.map.height,
            "tileset": Path(editor.tileset.path).name if editor.tileset.path else "",
            "layers": layers,
        }
        FileManager.save_json(path, data)


class NewMapDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Map")
        self.setModal(True)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 100000)
        self.width_spin.setValue(64)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 100000)
        self.height_spin.setValue(64)
        self.tile_spin = QSpinBox()
        self.tile_spin.setRange(1, 100000)
        self.tile_spin.setValue(DEFAULT_TILE_SIZE)
        form.addRow("Map Width (tiles)", self.width_spin)
        form.addRow("Map Height (tiles)", self.height_spin)
        form.addRow("Tile Size", self.tile_spin)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[int, int, int]:
        return self.width_spin.value(), self.height_spin.value(), self.tile_spin.value()


class TilePaletteCanvas(QWidget):
    selection_changed = Signal()

    def __init__(self, editor: "MainWindow") -> None:
        super().__init__()
        self.editor = editor
        self.setMouseTracking(True)
        self.dragging = False
        self.drag_start: Optional[QPoint] = None
        self.drag_current: Optional[QPoint] = None
        self.single_pick: Optional[QPoint] = None

    def sizeHint(self) -> QSize:
        tileset = self.editor.tileset
        if not tileset.is_loaded():
            return QSize(256, 256)
        cell = max(1, tileset.tile_size * self.editor.palette_zoom)
        return QSize(tileset.columns * cell, tileset.rows * cell)

    def update_size(self) -> None:
        self.setMinimumSize(self.sizeHint())
        self.resize(self.sizeHint())
        self.update()

    def cell_from_pos(self, pos: QPoint) -> tuple[int, int]:
        tileset = self.editor.tileset
        cell = max(1, tileset.tile_size * self.editor.palette_zoom)
        return pos.x() // cell, pos.y() // cell

    def tile_rect(self, tx: int, ty: int) -> QRect:
        tileset = self.editor.tileset
        cell = max(1, tileset.tile_size * self.editor.palette_zoom)
        return QRect(tx * cell, ty * cell, cell, cell)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self._paint_checkerboard(painter, self.rect(), 16)
        tileset = self.editor.tileset
        if not tileset.is_loaded():
            painter.setPen(self.palette().color(self.foregroundRole()))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Load a PNG tileset")
            return
        cell = max(1, tileset.tile_size * self.editor.palette_zoom)
        for row in range(tileset.rows):
            for col in range(tileset.columns):
                tile_id = row * tileset.columns + col + 1
                img = tileset.tile_image(tile_id)
                if img is None:
                    continue
                rect = QRect(col * cell, row * cell, cell, cell)
                painter.drawImage(rect, img)
                painter.setPen(QPen(QColor(40, 40, 40, 180), 1))
                painter.drawRect(rect.adjusted(0, 0, -1, -1))
                if cell >= 18:
                    painter.setPen(QColor(255, 255, 255, 160))
                    painter.setFont(QFont("Sans Serif", max(6, cell // 4)))
                    painter.drawText(rect.adjusted(2, 2, -2, -2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, str(tile_id))
        sel = self.editor.palette_selection
        if sel.is_valid():
            painter.setPen(QPen(QColor(255, 215, 0), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRect(sel.x * cell, sel.y * cell, sel.width * cell, sel.height * cell).adjusted(1, 1, -1, -1))
        hover = self.editor.palette_hover
        if hover is not None:
            painter.setPen(QPen(QColor(100, 200, 255), 2))
            painter.drawRect(self.tile_rect(hover.x(), hover.y()).adjusted(1, 1, -1, -1))
        if self.dragging and self.drag_start and self.drag_current:
            r = self.drag_rect()
            painter.setPen(QPen(QColor(255, 255, 255), 2, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(255, 255, 255, 40))
            painter.drawRect(r.adjusted(1, 1, -1, -1))

    def _paint_checkerboard(self, painter: QPainter, rect: QRect, size: int) -> None:
        c1 = QColor(80, 80, 80)
        c2 = QColor(100, 100, 100)
        y = rect.top()
        toggle = False
        while y < rect.bottom():
            x = rect.left()
            row_toggle = toggle
            while x < rect.right():
                painter.fillRect(QRect(x, y, size, size), c1 if row_toggle else c2)
                row_toggle = not row_toggle
                x += size
            toggle = not toggle
            y += size

    def drag_rect(self) -> QRect:
        if not (self.drag_start and self.drag_current):
            return QRect()
        a = self.drag_start
        b = self.drag_current
        x1, x2 = sorted((a.x(), b.x()))
        y1, y2 = sorted((a.y(), b.y()))
        cell = max(1, self.editor.tileset.tile_size * self.editor.palette_zoom)
        return QRect(x1 * cell, y1 * cell, (x2 - x1 + 1) * cell, (y2 - y1 + 1) * cell)

    def mousePressEvent(self, event) -> None:
        tileset = self.editor.tileset
        if not tileset.is_loaded():
            return
        tx, ty = self.cell_from_pos(event.position().toPoint())
        if not (0 <= tx < tileset.columns and 0 <= ty < tileset.rows):
            return
        self.setFocus()
        if self.editor.current_tool == Tool.RECTANGLE:
            self.dragging = True
            self.drag_start = QPoint(tx, ty)
            self.drag_current = QPoint(tx, ty)
            self.update()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.editor.select_single_tile(tx, ty)
        elif event.button() == Qt.MouseButton.RightButton:
            self.editor.select_single_tile(tx, ty)
        self.update()

    def mouseMoveEvent(self, event) -> None:
        tileset = self.editor.tileset
        if not tileset.is_loaded():
            return
        tx, ty = self.cell_from_pos(event.position().toPoint())
        if 0 <= tx < tileset.columns and 0 <= ty < tileset.rows:
            self.editor.palette_hover = QPoint(tx, ty)
        else:
            self.editor.palette_hover = None
        if self.dragging and self.drag_start is not None:
            self.drag_current = QPoint(max(0, min(tx, tileset.columns - 1)), max(0, min(ty, tileset.rows - 1)))
            self.editor.set_palette_selection_region(self.drag_start.x(), self.drag_start.y(), self.drag_current.x(), self.drag_current.y())
            self.update()
            return
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


class TilePalette(QWidget):
    def __init__(self, editor: "MainWindow") -> None:
        super().__init__()
        self.editor = editor
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        top = QHBoxLayout()
        self.single_preview = QLabel("Tile")
        self.single_preview.setFixedSize(88, 88)
        self.single_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.single_preview.setFrameShape(QFrame.Shape.StyledPanel)
        self.rect_preview = QLabel("Rectangle")
        self.rect_preview.setFixedSize(88, 88)
        self.rect_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rect_preview.setFrameShape(QFrame.Shape.StyledPanel)
        top.addWidget(self.single_preview)
        top.addWidget(self.rect_preview)
        top.addStretch(1)
        layout.addLayout(top)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.canvas = TilePaletteCanvas(editor)
        self.scroll.setWidget(self.canvas)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(self.scroll, 1)

    def refresh(self) -> None:
        self.canvas.update_size()
        self.update_previews()
        self.canvas.update()

    def update_previews(self) -> None:
        tileset = self.editor.tileset
        self.single_preview.setText("Tile")
        self.single_preview.setPixmap(QPixmap())
        self.rect_preview.setText("Rectangle")
        self.rect_preview.setPixmap(QPixmap())
        if not tileset.is_loaded():
            return
        tile_id = max(1, self.editor.selected_tile_id)
        img = tileset.transformed_tile(tile_id, self.editor.selected_transform.encode())
        if img is not None:
            pm = QPixmap.fromImage(img).scaled(self.single_preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.single_preview.setPixmap(pm)
            self.single_preview.setText("")
        stamp = self.editor.current_stamp_matrix()
        if stamp:
            preview = render_stamp_preview(self.editor, stamp, self.editor.selected_transform)
            if preview is not None:
                pm = QPixmap.fromImage(preview).scaled(self.rect_preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.rect_preview.setPixmap(pm)
                self.rect_preview.setText("")

    def wheelEvent(self, event) -> None:
        self.scroll.wheelEvent(event)


class LayerRowWidget(QWidget):
    def __init__(self, editor: "MainWindow", index: int) -> None:
        super().__init__()
        self.editor = editor
        self.index = index
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        self.vis_btn = QToolButton()
        self.vis_btn.setCheckable(True)
        self.vis_btn.clicked.connect(self.on_visibility)
        self.lock_btn = QToolButton()
        self.lock_btn.setCheckable(True)
        self.lock_btn.clicked.connect(self.on_lock)
        self.name_label = QLabel()
        self.name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.valueChanged.connect(self.on_opacity)
        layout.addWidget(self.vis_btn)
        layout.addWidget(self.lock_btn)
        layout.addWidget(self.name_label, 1)
        layout.addWidget(self.opacity_slider, 1)
        self.refresh()

    def refresh(self) -> None:
        layer = self.editor.map.layers[self.index]
        self.name_label.setText(layer.name)
        self.vis_btn.setText("V")
        self.vis_btn.setChecked(layer.visible)
        self.lock_btn.setText("L")
        self.lock_btn.setChecked(layer.locked)
        self.opacity_slider.blockSignals(True)
        self.opacity_slider.setValue(int(layer.opacity * 100))
        self.opacity_slider.blockSignals(False)
        self.setStyleSheet("background: rgba(120,160,220,40);" if self.index == self.editor.active_layer_index else "")

    def on_visibility(self) -> None:
        self.editor.set_layer_visibility(self.index, self.vis_btn.isChecked())

    def on_lock(self) -> None:
        self.editor.set_layer_locked(self.index, self.lock_btn.isChecked())

    def on_opacity(self, value: int) -> None:
        self.editor.set_layer_opacity(self.index, value / 100.0)


class LayerPanel(QWidget):
    def __init__(self, editor: "MainWindow") -> None:
        super().__init__()
        self.editor = editor
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        btns = QHBoxLayout()
        self.add_btn = QPushButton("Add")
        self.del_btn = QPushButton("Delete")
        self.dup_btn = QPushButton("Duplicate")
        self.up_btn = QPushButton("Up")
        self.down_btn = QPushButton("Down")
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
        for i, layer in enumerate(self.editor.map.layers):
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 34))
            self.list.addItem(item)
            widget = LayerRowWidget(self.editor, i)
            self.list.setItemWidget(item, widget)
        if self.editor.active_layer_index >= 0 and self.editor.active_layer_index < self.list.count():
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
        self.tileset_label = QLabel("Tileset: -")
        for lbl in [self.mouse_label, self.layer_label, self.tile_label, self.zoom_label, self.tool_label, self.map_label, self.tileset_label]:
            self.addPermanentWidget(lbl)

    def update_all(self) -> None:
        self.mouse_label.setText(f"Tile: {self.editor.hover_tile_text} | Pixel: {self.editor.hover_pixel_text}")
        self.layer_label.setText(f"Layer: {self.editor.active_layer_name()}")
        self.tile_label.setText(f"Selected: {self.editor.selected_tile_id}")
        self.zoom_label.setText(f"Zoom: {int(self.editor.camera.zoom * 100)}%")
        self.tool_label.setText(f"Tool: {self.editor.current_tool.value}")
        self.map_label.setText(f"Map: {self.editor.map.width}x{self.editor.map.height} @ {self.editor.map.tile_size}")
        if self.editor.tileset.is_loaded():
            self.tileset_label.setText(f"Tileset: {self.editor.tileset.columns}x{self.editor.tileset.rows} tiles")
        else:
            self.tileset_label.setText("Tileset: none")


def transform_matrix(matrix: list[list[int]], transform: TileTransform) -> list[list[int]]:
    if not matrix:
        return []
    data = [row[:] for row in matrix]
    if transform.hflip:
        data = [list(reversed(row)) for row in data]
    if transform.vflip:
        data = list(reversed(data))
    rot = transform.rotation % 4
    for _ in range(rot):
        data = [list(row) for row in zip(*data[::-1])]
    return data


def nine_slice_matrix(source: list[list[int]], width: int, height: int) -> list[list[int]]:
    if not source or width <= 0 or height <= 0:
        return []
    sh = len(source)
    sw = len(source[0]) if source[0] else 0
    if sw == 0 or sh == 0:
        return []
    result = [[0 for _ in range(width)] for _ in range(height)]

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


def render_stamp_preview(editor: "MainWindow", stamp: list[list[int]], transform: TileTransform) -> Optional[QImage]:
    tileset = editor.tileset
    if not tileset.is_loaded() or not stamp:
        return None
    matrix = transform_matrix(stamp, transform)
    h = len(matrix)
    w = len(matrix[0]) if h else 0
    if w <= 0 or h <= 0:
        return None
    cell = tileset.tile_size
    image = QImage(w * cell, h * cell, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    for y, row in enumerate(matrix):
        for x, tile_id in enumerate(row):
            if tile_id <= 0:
                continue
            img = tileset.transformed_tile(tile_id, 0)
            if img is not None:
                painter.drawImage(QRect(x * cell, y * cell, cell, cell), img)
    painter.end()
    return image


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
        ts = self.editor.map.tile_size
        x = int(world.x() // ts)
        y = int(world.y() // ts)
        if 0 <= x < self.editor.map.width and 0 <= y < self.editor.map.height:
            return QPoint(x, y)
        return None

    def mouse_pixels(self, pos: QPointF) -> tuple[int, int]:
        world = self.view_to_world(pos.x(), pos.y())
        return int(world.x()), int(world.y())

    def tile_rect(self, tx: int, ty: int) -> QRectF:
        ts = self.editor.map.tile_size
        zoom = self.editor.camera.zoom
        x = (tx * ts - self.editor.camera.x) * zoom
        y = (ty * ts - self.editor.camera.y) * zoom
        return QRectF(x, y, ts * zoom, ts * zoom)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self._paint_background(painter)
        map_model = self.editor.map
        tileset = self.editor.tileset
        zoom = self.editor.camera.zoom
        ts = map_model.tile_size
        view_rect = self.rect()
        world_left = self.editor.camera.x
        world_top = self.editor.camera.y
        world_right = world_left + view_rect.width() / zoom
        world_bottom = world_top + view_rect.height() / zoom
        x0 = max(0, int(world_left // ts) - 1)
        y0 = max(0, int(world_top // ts) - 1)
        x1 = min(map_model.width, int(math.ceil(world_right / ts)) + 1)
        y1 = min(map_model.height, int(math.ceil(world_bottom / ts)) + 1)
        for layer in map_model.layers:
            if not layer.visible:
                continue
            painter.save()
            painter.setOpacity(layer.opacity)
            for y in range(y0, y1):
                base = y * layer.width
                for x in range(x0, x1):
                    idx = base + x
                    tile_id = layer.tile_ids[idx]
                    if tile_id <= 0:
                        continue
                    flags = layer.transforms[idx]
                    img = tileset.transformed_tile(tile_id, flags) if tileset.is_loaded() else None
                    if img is None:
                        continue
                    rect = QRectF((x * ts - self.editor.camera.x) * zoom, (y * ts - self.editor.camera.y) * zoom, ts * zoom, ts * zoom)
                    painter.drawImage(rect, img)
            painter.restore()
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
            self._checkerboard(painter, self.rect(), 16)
        else:
            painter.fillRect(self.rect(), editor.background_color)

    def _checkerboard(self, painter: QPainter, rect: QRect, size: int) -> None:
        c1 = QColor(54, 54, 54)
        c2 = QColor(65, 65, 65)
        y = rect.top()
        flip = False
        while y < rect.bottom() + size:
            x = rect.left()
            row_flip = flip
            while x < rect.right() + size:
                painter.fillRect(QRect(x, y, size, size), c1 if row_flip else c2)
                row_flip = not row_flip
                x += size
            flip = not flip
            y += size

    def _paint_grid(self, painter: QPainter, x0: int, y0: int, x1: int, y1: int) -> None:
        map_model = self.editor.map
        ts = map_model.tile_size
        zoom = self.editor.camera.zoom
        pen = QPen(self.editor.grid_color, 1)
        painter.setPen(pen)
        for x in range(x0, x1 + 1):
            sx = (x * ts - self.editor.camera.x) * zoom
            painter.drawLine(int(sx), 0, int(sx), self.height())
        for y in range(y0, y1 + 1):
            sy = (y * ts - self.editor.camera.y) * zoom
            painter.drawLine(0, int(sy), self.width(), int(sy))

    def _paint_region_outline(self, painter: QPainter, region: SelectionRegion, color: QColor, style: Qt.PenStyle, fill: Optional[QColor] = None) -> None:
        if not region.is_valid():
            return
        rect = QRectF((region.x * self.editor.map.tile_size - self.editor.camera.x) * self.editor.camera.zoom, (region.y * self.editor.map.tile_size - self.editor.camera.y) * self.editor.camera.zoom, region.width * self.editor.map.tile_size * self.editor.camera.zoom, region.height * self.editor.map.tile_size * self.editor.camera.zoom)
        painter.setPen(QPen(color, 2, style))
        painter.setBrush(fill if fill is not None else Qt.BrushStyle.NoBrush)
        painter.drawRect(rect.adjusted(1, 1, -1, -1))

    def _paint_stamp_preview(self, painter: QPainter, region: SelectionRegion) -> None:
        if not region.is_valid() or not self.editor.brush_stamp_available():
            return
        stamp = self.editor.current_stamp_matrix()
        if not stamp:
            return
        transformed = transform_matrix(stamp, self.editor.selected_transform)
        sized = nine_slice_matrix(transformed, region.width, region.height) if self.editor.current_tool == Tool.RECTANGLE else transformed
        if not sized:
            return
        self._paint_matrix_preview(painter, region.x, region.y, sized, 0.45)

    def _paint_stamp_at_hover(self, painter: QPainter, tile_x: int, tile_y: int, alpha: float) -> None:
        stamp = self.editor.current_stamp_matrix()
        if not stamp:
            return
        if self.editor.current_tool == Tool.RECTANGLE:
            self._paint_matrix_preview(painter, tile_x, tile_y, transform_matrix(stamp, self.editor.selected_transform), alpha)
        else:
            self._paint_matrix_preview(painter, tile_x, tile_y, [[self.editor.selected_tile_id]], alpha)

    def _paint_matrix_preview(self, painter: QPainter, x: int, y: int, matrix: list[list[int]], alpha: float) -> None:
        tileset = self.editor.tileset
        if not tileset.is_loaded():
            return
        ts = self.editor.map.tile_size
        zoom = self.editor.camera.zoom
        painter.save()
        painter.setOpacity(alpha)
        for yy, row in enumerate(matrix):
            for xx, tile_id in enumerate(row):
                if tile_id <= 0:
                    continue
                img = tileset.transformed_tile(tile_id, 0)
                if img is None:
                    continue
                rect = QRectF(((x + xx) * ts - self.editor.camera.x) * zoom, ((y + yy) * ts - self.editor.camera.y) * zoom, ts * zoom, ts * zoom)
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
        pos = event.position().toPoint()
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
                self.editor.paint_cell(mouse_tile.x(), mouse_tile.y(), 0, TileTransform(), self.stroke_changes, self.stroke_seen)
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
                    self.editor.paint_cell(pt[0], pt[1], 0, TileTransform(), self.stroke_changes, self.stroke_seen)
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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setWindowTitle("Tilemap Editor")
        self.resize(1600, 1000)
        self.settings = QSettings(APP_ORG, APP_NAME)
        self.undo_manager = UndoManager(100)
        self.map = TileMap(64, 64, DEFAULT_TILE_SIZE)
        self.tileset = TileSetModel()
        self.camera = Camera()
        self.current_tool = Tool.SINGLE
        self.selected_tile_id = 1
        self.selected_transform = TileTransform()
        self.palette_zoom = 2
        self.palette_selection = SelectionRegion(0, 0, 0, 0)
        self.palette_hover: Optional[QPoint] = None
        self.brush_selection: list[list[int]] = []
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
        self.recovery_active = False
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
        self.setCentralWidget(splitter)
        self.toolbar = QToolBar("Toolbar")
        self.toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)
        self.status = EditorStatusBar(self)
        self.setStatusBar(self.status)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _make_action(self, text: str, slot: Callable[[], None], shortcut: Optional[str] = None, checkable: bool = False) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.setCheckable(checkable)
        return action

    def _build_actions(self) -> None:
        self.act_new = self._make_action("New Map...", self.new_map, "Ctrl+N")
        self.act_open = self._make_action("Open Map...", self.open_map, "Ctrl+O")
        self.act_save = self._make_action("Save", self.save_map, "Ctrl+S")
        self.act_save_as = self._make_action("Save As...", self.save_map_as, "Ctrl+Shift+S")
        self.act_export = self._make_action("Export Layers as JSON...", self.export_layers)
        self.act_load_tileset = self._make_action("Load Tileset...", self.load_tileset)
        self.act_change_tile_size = self._make_action("Change Tile Size...", self.change_tile_size)
        self.act_exit = self._make_action("Exit", self.close)
        self.act_undo = self._make_action("Undo", self.undo, "Ctrl+Z")
        self.act_redo = self._make_action("Redo", self.redo, "Ctrl+Y")
        self.act_single = self._make_action("Single Draw", lambda: self.set_tool(Tool.SINGLE), "I")
        self.act_rect = self._make_action("Rectangle Brush", lambda: self.set_tool(Tool.RECTANGLE), "R")
        self.act_fill = self._make_action("Fill", lambda: self.set_tool(Tool.FILL), "F")
        self.act_eyedropper = self._make_action("Eyedropper", lambda: self.set_tool(Tool.EYEDROPPER), "E")
        self.act_erase = self._make_action("Erase", lambda: self.set_tool(Tool.ERASE), "B")
        self.act_selection = self._make_action("Selection Tool", lambda: self.set_tool(Tool.SELECTION), "S")
        self.act_grid = self._make_action("Grid", self.toggle_grid, "G", True)
        self.act_grid.setChecked(True)
        self.act_zoom_in = self._make_action("Zoom In", self.zoom_in, "Ctrl++")
        self.act_zoom_out = self._make_action("Zoom Out", self.zoom_out, "Ctrl+-")
        self.act_reset_zoom = self._make_action("Reset Zoom", self.reset_zoom)
        self.act_bg_color = self._make_action("Background Color...", self.pick_background_color)
        self.act_grid_color = self._make_action("Grid Color...", self.pick_grid_color)
        self.act_checkerboard = self._make_action("Checkerboard Background", self.toggle_checkerboard, checkable=True)
        self.act_checkerboard.setChecked(True)
        self.act_load_tileset.triggered.connect(self.load_tileset)
        self.recent_menu = QMenu("Recent Files", self)

    def _build_menus(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("File")
        for a in [self.act_new, self.act_open, self.act_save, self.act_save_as, self.act_export, self.act_load_tileset, self.act_change_tile_size]:
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

        for a in [self.act_new, self.act_open, self.act_save, self.act_load_tileset, self.act_undo, self.act_redo, self.act_single, self.act_rect, self.act_fill, self.act_eyedropper, self.act_erase, self.act_grid, self.act_zoom_in, self.act_zoom_out, self.act_reset_zoom]:
            self.toolbar.addAction(a)

    def apply_dark_theme(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
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

    def refresh_all(self) -> None:
        self.refresh_views()
        self.layer_panel.refresh()
        self.palette_panel.refresh()
        self.refresh_status()
        self.update_window_title()

    def refresh_views(self) -> None:
        self.map_view.update()
        self.palette_panel.canvas.update()
        self.palette_panel.update_previews()
        self.layer_panel.update_rows()
        self.status.update_all()

    def refresh_status(self) -> None:
        if self.hover_tile is not None:
            self.hover_tile_text = f"{self.hover_tile.x()}, {self.hover_tile.y()}"
        else:
            self.hover_tile_text = "-"
        if self.hover_pixel is not None:
            self.hover_pixel_text = f"{self.hover_pixel[0]}, {self.hover_pixel[1]}"
        else:
            self.hover_pixel_text = "-"
        self.status.update_all()

    def update_window_title(self) -> None:
        name = Path(self.current_file).name if self.current_file else "Untitled"
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

    def brush_stamp_available(self) -> bool:
        return bool(self.current_stamp_matrix())

    def current_stamp_matrix(self) -> list[list[int]]:
        if self.brush_selection:
            return [row[:] for row in self.brush_selection]
        if self.palette_selection.is_valid() and self.tileset.is_loaded():
            return self.extract_tileset_matrix(self.palette_selection)
        if self.selected_tile_id > 0:
            return [[self.selected_tile_id]]
        return []

    def extract_tileset_matrix(self, region: SelectionRegion) -> list[list[int]]:
        tileset = self.tileset
        if not tileset.is_loaded() or not region.is_valid():
            return []
        matrix: list[list[int]] = []
        for y in range(region.y, region.y + region.height):
            row = []
            for x in range(region.x, region.x + region.width):
                tile_id = y * tileset.columns + x + 1
                row.append(tile_id if 1 <= tile_id <= tileset.count() else 0)
            matrix.append(row)
        return matrix

    def select_single_tile(self, tx: int, ty: int) -> None:
        self.palette_selection = SelectionRegion(tx, ty, 1, 1)
        self.selected_tile_id = ty * self.tileset.columns + tx + 1 if self.tileset.is_loaded() else 1
        self.selected_transform = TileTransform()
        self.brush_selection = [[self.selected_tile_id]] if self.selected_tile_id > 0 else []
        self.refresh_views()

    def set_palette_selection_region(self, x0: int, y0: int, x1: int, y1: int) -> None:
        x1 = max(0, min(x1, self.tileset.columns - 1))
        y1 = max(0, min(y1, self.tileset.rows - 1))
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        self.palette_selection = SelectionRegion(x0, y0, x1 - x0 + 1, y1 - y0 + 1)
        self.selected_tile_id = y0 * self.tileset.columns + x0 + 1 if self.tileset.is_loaded() else 1
        self.refresh_views()

    def commit_palette_stamp_selection(self) -> None:
        self.brush_selection = self.current_stamp_matrix()
        self.palette_panel.update_previews()

    def select_current_tile_from_map(self, tile_id: int, transform_flags: int) -> None:
        self.selected_tile_id = max(0, tile_id)
        self.selected_transform = TileTransform.decode(transform_flags)
        self.palette_selection = SelectionRegion(0, 0, 0, 0)
        self.refresh_views()

    def set_tool(self, tool: Tool) -> None:
        self.current_tool = tool
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
        old_zoom = self.camera.zoom
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
        ts = self.map.tile_size
        zoom = self.camera.zoom
        rect = QRect(int((region.x * ts - self.camera.x) * zoom) - 4, int((region.y * ts - self.camera.y) * zoom) - 4, int(region.width * ts * zoom) + 8, int(region.height * ts * zoom) + 8)
        self.map_view.update(rect)

    def paint_cell(self, x: int, y: int, tile_id: int, transform: TileTransform, change_list: Optional[list[StrokeChange]] = None, seen: Optional[set[int]] = None) -> None:
        layer = self.active_layer()
        if layer is None or layer.locked or not layer.visible or not layer.in_bounds(x, y):
            return
        idx = layer.index(x, y)
        if seen is not None and idx in seen:
            return
        old_tile, old_transform = layer.get_by_index(idx)
        if old_tile == tile_id and old_transform == transform.encode():
            return
        layer.set_by_index(idx, tile_id, transform.encode())
        if change_list is not None and seen is not None:
            change_list.append(StrokeChange(self.active_layer_index, idx, old_tile, old_transform.encode(), tile_id, transform.encode()))
            seen.add(idx)
        self.map_viewport_update_from_region(SelectionRegion(x, y, 1, 1))
        self.set_modified()

    def paint_current_brush_at(self, x: int, y: int, change_list: Optional[list[StrokeChange]] = None, seen: Optional[set[int]] = None) -> None:
        stamp = self.current_stamp_matrix()
        if not stamp:
            return
        if len(stamp) == 1 and len(stamp[0]) == 1:
            self.paint_cell(x, y, stamp[0][0], self.selected_transform, change_list, seen)
            return
        matrix = transform_matrix(stamp, self.selected_transform)
        for yy, row in enumerate(matrix):
            for xx, tile_id in enumerate(row):
                self.paint_cell(x + xx, y + yy, tile_id, TileTransform(), change_list, seen)

    def erase_cell(self, x: int, y: int, record_undo: bool = False) -> None:
        layer = self.active_layer()
        if layer is None or layer.locked or not layer.visible or not layer.in_bounds(x, y):
            return
        idx = layer.index(x, y)
        old_tile, old_transform = layer.get_by_index(idx)
        if old_tile == 0:
            return
        layer.set_by_index(idx, 0, 0)
        if record_undo:
            def undo_one() -> None:
                layer.set_by_index(idx, old_tile, old_transform.encode())
            def redo_one() -> None:
                layer.set_by_index(idx, 0, 0)
            self.undo_manager.push(UndoAction("Erase", undo_one, redo_one))
        self.map_viewport_update_from_region(SelectionRegion(x, y, 1, 1))
        self.set_modified()

    def commit_stroke(self, changes: list[StrokeChange], description: str) -> None:
        if not changes:
            return
        before = [StrokeChange(c.layer_index, c.index, c.new_tile, c.new_transform, c.old_tile, c.old_transform) for c in changes]
        after = [deepcopy(c) for c in changes]
        def apply(items: list[StrokeChange]) -> None:
            for c in items:
                if 0 <= c.layer_index < len(self.map.layers):
                    layer = self.map.layers[c.layer_index]
                    layer.set_by_index(c.index, c.new_tile, c.new_transform)
        apply(before)
        self.undo_manager.push(UndoAction(description, lambda: apply(before), lambda: apply(after)))
        self.set_modified()
        self.refresh_all()

    def commit_rectangle_stamp(self, region: SelectionRegion) -> None:
        if not region.is_valid() or not self.brush_stamp_available():
            return
        source = transform_matrix(self.current_stamp_matrix(), self.selected_transform)
        matrix = nine_slice_matrix(source, region.width, region.height)
        if not matrix:
            return
        changes: list[StrokeChange] = []
        seen: set[int] = set()
        for yy, row in enumerate(matrix):
            for xx, tile_id in enumerate(row):
                self.paint_cell(region.x + xx, region.y + yy, tile_id, TileTransform(), changes, seen)
        if not changes:
            return
        before = [StrokeChange(c.layer_index, c.index, c.new_tile, c.new_transform, c.old_tile, c.old_transform) for c in changes]
        after = [deepcopy(c) for c in changes]
        def apply(items: list[StrokeChange]) -> None:
            for c in items:
                self.map.layers[c.layer_index].set_by_index(c.index, c.new_tile, c.new_transform)
        apply(before)
        self.undo_manager.push(UndoAction("Rectangle Brush", lambda: apply(before), lambda: apply(after)))
        self.refresh_all()
        self.set_modified()

    def flood_fill(self, x: int, y: int) -> None:
        layer = self.active_layer()
        if layer is None or layer.locked or not layer.visible:
            return
        if not layer.in_bounds(x, y):
            return
        target_id, target_transform = layer.get(x, y)
        new_stamp = self.current_stamp_matrix()
        if len(new_stamp) == 1 and len(new_stamp[0]) == 1:
            new_id = new_stamp[0][0]
            new_transform = self.selected_transform.encode()
        else:
            new_id = new_stamp[0][0] if new_stamp else 0
            new_transform = 0
        if target_id == new_id and target_transform.encode() == new_transform:
            return
        q = deque([(x, y)])
        visited = set()
        changes: list[StrokeChange] = []
        while q:
            cx, cy = q.popleft()
            if (cx, cy) in visited or not layer.in_bounds(cx, cy):
                continue
            visited.add((cx, cy))
            cur_id, cur_transform = layer.get(cx, cy)
            if cur_id != target_id or cur_transform.encode() != target_transform.encode():
                continue
            idx = layer.index(cx, cy)
            changes.append(StrokeChange(self.active_layer_index, idx, cur_id, cur_transform.encode(), new_id, new_transform))
            layer.set_by_index(idx, new_id, new_transform)
            q.extend([(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)])
        if not changes:
            return
        before = [StrokeChange(c.layer_index, c.index, c.new_tile, c.new_transform, c.old_tile, c.old_transform) for c in changes]
        after = [deepcopy(c) for c in changes]
        def apply(items: list[StrokeChange]) -> None:
            for c in items:
                self.map.layers[c.layer_index].set_by_index(c.index, c.new_tile, c.new_transform)
        self.undo_manager.push(UndoAction("Fill", lambda: apply(before), lambda: apply(after)))
        self.refresh_all()
        self.set_modified()

    def pick_from_map(self, x: int, y: int) -> None:
        layer = self.active_layer()
        if layer is None or not layer.in_bounds(x, y):
            return
        tile_id, transform = layer.get(x, y)
        self.select_current_tile_from_map(tile_id, transform.encode())

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
                old_tile, old_transform = layer.get_by_index(idx)
                if old_tile == 0:
                    continue
                layer.set_by_index(idx, 0, 0)
                changes.append(StrokeChange(self.active_layer_index, idx, old_tile, old_transform.encode(), 0, 0))
        if not changes:
            return
        before = [StrokeChange(c.layer_index, c.index, c.new_tile, c.new_transform, c.old_tile, c.old_transform) for c in changes]
        after = [deepcopy(c) for c in changes]
        def apply(items: list[StrokeChange]) -> None:
            for c in items:
                self.map.layers[c.layer_index].set_by_index(c.index, c.new_tile, c.new_transform)
        self.undo_manager.push(UndoAction("Clear Region", lambda: apply(before), lambda: apply(after)))
        self.refresh_all()
        self.set_modified()

    def capture_layers_state(self) -> dict[str, Any]:
        return {"layers": [deepcopy(layer.to_dict()) for layer in self.map.layers], "active": self.active_layer_index}

    def restore_layers_state(self, snapshot: dict[str, Any]) -> None:
        layers_data = snapshot.get("layers", [])
        self.map.layers = [TileLayer.from_dict(ld, self.map.width, self.map.height) for ld in layers_data] if isinstance(layers_data, list) else [TileLayer(self.map.width, self.map.height)]
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
        after = self.capture_layers_state()
        self.push_layers_undo(before, after, "Layer Visibility")

    def set_layer_locked(self, index: int, locked: bool) -> None:
        if not (0 <= index < len(self.map.layers)):
            return
        before = self.capture_layers_state()
        self.map.layers[index].locked = locked
        after = self.capture_layers_state()
        self.push_layers_undo(before, after, "Layer Lock")

    def set_layer_opacity(self, index: int, opacity: float) -> None:
        if not (0 <= index < len(self.map.layers)):
            return
        before = self.capture_layers_state()
        self.map.layers[index].opacity = max(0.0, min(1.0, opacity))
        after = self.capture_layers_state()
        self.push_layers_undo(before, after, "Layer Opacity")

    def add_layer(self) -> None:
        before = self.capture_layers_state()
        self.map.layers.append(TileLayer(self.map.width, self.map.height, f"Layer {len(self.map.layers) + 1}"))
        self.active_layer_index = len(self.map.layers) - 1
        after = self.capture_layers_state()
        self.push_layers_undo(before, after, "Add Layer")

    def duplicate_current_layer(self) -> None:
        layer = self.active_layer()
        if layer is None:
            return
        before = self.capture_layers_state()
        new_layer = layer.clone()
        new_layer.name = f"{layer.name} Copy"
        self.map.layers.insert(self.active_layer_index + 1, new_layer)
        self.active_layer_index += 1
        after = self.capture_layers_state()
        self.push_layers_undo(before, after, "Duplicate Layer")

    def delete_current_layer(self) -> None:
        if len(self.map.layers) <= 1:
            QMessageBox.information(self, "Delete Layer", "A map must have at least one layer.")
            return
        before = self.capture_layers_state()
        del self.map.layers[self.active_layer_index]
        self.active_layer_index = max(0, min(self.active_layer_index, len(self.map.layers) - 1))
        after = self.capture_layers_state()
        self.push_layers_undo(before, after, "Delete Layer")

    def move_layer(self, direction: int) -> None:
        new_index = self.active_layer_index + direction
        if not (0 <= self.active_layer_index < len(self.map.layers)) or not (0 <= new_index < len(self.map.layers)):
            return
        before = self.capture_layers_state()
        self.map.layers[self.active_layer_index], self.map.layers[new_index] = self.map.layers[new_index], self.map.layers[self.active_layer_index]
        self.active_layer_index = new_index
        after = self.capture_layers_state()
        self.push_layers_undo(before, after, "Move Layer")

    def rename_current_layer(self) -> None:
        layer = self.active_layer()
        if layer is None:
            return
        text, ok = QInputDialog.getText(self, "Rename Layer", "Layer Name:", text=layer.name)
        if not ok or not text.strip():
            return
        before = self.capture_layers_state()
        layer.name = text.strip()
        after = self.capture_layers_state()
        self.push_layers_undo(before, after, "Rename Layer")

    def set_tool_shortcut_state(self) -> None:
        pass

    def clear_map_selection(self) -> None:
        self.map_selection = SelectionRegion()
        self.refresh_views()

    def delete_selection(self) -> None:
        if self.map_selection.is_valid():
            self.commit_region_clear(self.map_selection)
            self.map_selection = SelectionRegion()
            return
        if self.hover_tile is not None:
            self.erase_cell(self.hover_tile.x(), self.hover_tile.y())

    def change_tile_size(self) -> None:
        if not self.tileset.is_loaded():
            QMessageBox.information(self, "Change Tile Size", "Load a tileset first.")
            return
        value, ok = QInputDialog.getInt(self, "Change Tile Size", "Tile size:", value=self.tileset.tile_size, min=1, max=100000)
        if not ok:
            return
        before = self.tileset.snapshot()
        try:
            self.tileset.load(self.tileset.path, value)
        except Exception as exc:
            QMessageBox.critical(self, "Change Tile Size Failed", str(exc))
            self.tileset.restore(before)
            return
        after = self.tileset.snapshot()
        self.undo_manager.push(UndoAction("Tileset Change", lambda: self.tileset.restore(before), lambda: self.tileset.restore(after)))
        self.set_modified()
        self.palette_panel.refresh()
        self.refresh_views()

    def load_tileset(self) -> None:
        if not self.maybe_save_current():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Load Tileset", "", "PNG Images (*.png)")
        if not path:
            return
        size_default = self.tileset.tile_size if self.tileset.is_loaded() else self.map.tile_size if self.map.tile_size > 0 else DEFAULT_TILE_SIZE
        tile_size, ok = QInputDialog.getInt(self, "Tileset Tile Size", "Tile size:", value=size_default, min=1, max=100000)
        if not ok:
            return
        before = self.tileset.snapshot()
        try:
            self.tileset.load(path, tile_size)
            self.map.tileset_path = path
        except Exception as exc:
            QMessageBox.critical(self, "Load Tileset", str(exc))
            return
        after = self.tileset.snapshot()
        self.undo_manager.push(UndoAction("Load Tileset", lambda: self.tileset.restore(before), lambda: self.tileset.restore(after)))
        self.selected_tile_id = 1
        self.palette_selection = SelectionRegion(0, 0, 1, 1)
        self.brush_selection = self.current_stamp_matrix()
        self.set_modified()
        self.palette_panel.refresh()
        self.refresh_all()
        self.add_recent_file(path)

    def new_map(self) -> None:
        if not self.maybe_save_current():
            return
        dlg = NewMapDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        width, height, tile_size = dlg.values()
        self.map = TileMap(width, height, tile_size)
        self.camera = Camera()
        self.undo_manager.clear()
        self.current_file = ""
        self.selected_tile_id = 1
        self.selected_transform = TileTransform()
        self.palette_selection = SelectionRegion()
        self.map_selection = SelectionRegion()
        self.active_layer_index = 0
        self.modified = False
        self.refresh_all()

    def open_map(self) -> None:
        if not self.maybe_save_current():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Map", "", "Map JSON (*.json)")
        if not path:
            return
        self.load_map_from_path(path)

    def save_map(self) -> None:
        if not self.current_file:
            self.save_map_as()
            return
        self.save_to_path(self.current_file)

    def save_map_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Map As", self.current_file or "untitled.json", "Map JSON (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        self.save_to_path(path)

    def save_to_path(self, path: str) -> None:
        editor_state = self.editor_state_dict()
        data = self.map.to_dict(editor_state)
        try:
            FileManager.save_json(path, data)
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", f"Could not save map.\n\n{exc}")
            return
        self.current_file = path
        self.set_modified(False)
        FileManager.save_recent(self.settings, path)
        self.delete_recovery_file()
        self.refresh_recent_menu()
        self.refresh_status()
        self.update_window_title()

    def export_layers(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Layers as JSON", "layers_runtime.json", "JSON (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            ExportManager.export_runtime_json(self, path)
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))
            return
        QMessageBox.information(self, "Export Layers", f"Exported to:\n{path}")

    def load_map_from_path(self, path: str) -> None:
        try:
            data = FileManager.load_json(path)
            loaded_map, raw = TileMap.from_dict(data)
        except Exception as exc:
            QMessageBox.critical(self, "Open Map Failed", f"Could not open map.\n\n{exc}")
            return
        self.map = loaded_map
        camera_data = raw.get("camera", {}) if isinstance(raw, dict) else {}
        if isinstance(camera_data, dict):
            self.camera.x = float(camera_data.get("x", 0.0))
            self.camera.y = float(camera_data.get("y", 0.0))
            self.camera.set_zoom_to_factor(float(camera_data.get("zoom", 1.0)))
        grid_data = raw.get("grid", {}) if isinstance(raw, dict) else {}
        if isinstance(grid_data, dict):
            self.grid_visible = bool(grid_data.get("visible", True))
            grid_color = grid_data.get("color", "#505050")
            self.grid_color = QColor(str(grid_color)) if QColor(str(grid_color)).isValid() else QColor(80, 80, 80)
        editor_data = raw.get("editor", {}) if isinstance(raw, dict) else {}
        if isinstance(editor_data, dict):
            self.background_color = QColor(str(editor_data.get("backgroundColor", "#1e1e1e")))
            self.checkerboard_background = bool(editor_data.get("checkerboard", True))
            self.selected_tile_id = int(editor_data.get("selectedTile", 1))
            self.selected_transform = TileTransform.from_dict(editor_data.get("transform", {}))
            self.palette_selection = SelectionRegion.from_dict(editor_data.get("selection", {}))
            self.map_selection = SelectionRegion.from_dict(editor_data.get("mapSelection", {}))
            self.current_tool = Tool(editor_data.get("tool", Tool.SINGLE.value)) if editor_data.get("tool", Tool.SINGLE.value) in Tool._value2member_map_ else Tool.SINGLE
        self.current_file = path
        self.modified = False
        self.undo_manager.clear()
        if self.map.tileset_path and Path(self.map.tileset_path).exists():
            try:
                self.tileset.load(self.map.tileset_path, self.map.tile_size)
            except Exception:
                self.tileset.clear()
        else:
            self.tileset.clear()
        self.active_layer_index = max(0, min(int(raw.get("activeLayer", 0)) if isinstance(raw, dict) else 0, len(self.map.layers) - 1))
        if self.palette_selection.is_valid() and self.tileset.is_loaded():
            self.brush_selection = self.current_stamp_matrix()
        else:
            self.brush_selection = []
        self.refresh_all()
        FileManager.save_recent(self.settings, path)
        self.refresh_recent_menu()
        self.update_window_title()

    def editor_state_dict(self) -> dict[str, Any]:
        return {
            "camera": {"x": self.camera.x, "y": self.camera.y, "zoom": self.camera.zoom},
            "grid": {"visible": self.grid_visible, "color": self.grid_color.name()},
            "editor": {
                "backgroundColor": self.background_color.name(),
                "checkerboard": self.checkerboard_background,
                "tool": self.current_tool.value,
                "selectedTile": self.selected_tile_id,
                "transform": self.selected_transform.to_dict(),
                "selection": self.palette_selection.to_dict(),
                "mapSelection": self.map_selection.to_dict(),
                "activeLayer": self.active_layer_index,
            },
            "activeLayer": self.active_layer_index,
        }

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

    def commit_stroke(self, changes: list[StrokeChange], description: str) -> None:
        if not changes:
            return
        before = [StrokeChange(c.layer_index, c.index, c.old_tile, c.old_transform, c.new_tile, c.new_transform) for c in changes]
        after = [StrokeChange(c.layer_index, c.index, c.new_tile, c.new_transform, c.old_tile, c.old_transform) for c in changes]
        def apply(items: list[StrokeChange]) -> None:
            for c in items:
                if 0 <= c.layer_index < len(self.map.layers):
                    self.map.layers[c.layer_index].set_by_index(c.index, c.new_tile, c.new_transform)
        self.undo_manager.push(UndoAction(description, lambda: apply(before), lambda: apply(after)))
        self.refresh_all()
        self.set_modified()

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

    def check_recovery(self) -> None:
        recovery = FileManager.recovery_path()
        if not recovery.exists():
            return
        choice = QMessageBox.question(self, "Recover Autosave", "A recovery file was found. Load it?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if choice == QMessageBox.StandardButton.Yes:
            try:
                self.load_map_from_path(str(recovery))
                self.recovery_active = True
            except Exception as exc:
                QMessageBox.critical(self, "Recovery Failed", str(exc))
        else:
            try:
                recovery.unlink(missing_ok=True)
            except Exception:
                pass

    def autosave(self) -> None:
        if not self.modified:
            return
        path = FileManager.recovery_path()
        try:
            data = self.map.to_dict(self.editor_state_dict())
            FileManager.save_json(str(path), data)
        except Exception:
            return

    def delete_recovery_file(self) -> None:
        try:
            FileManager.recovery_path().unlink(missing_ok=True)
        except Exception:
            pass

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
            lower = path.lower()
            if lower.endswith(".png"):
                if not self.maybe_save_current():
                    return
                try:
                    size_default = self.tileset.tile_size if self.tileset.is_loaded() else DEFAULT_TILE_SIZE
                    tile_size, ok = QInputDialog.getInt(self, "Tileset Tile Size", "Tile size:", value=size_default, min=1, max=100000)
                    if not ok:
                        return
                    self.tileset.load(path, tile_size)
                    self.map.tileset_path = path
                    self.palette_selection = SelectionRegion(0, 0, 1, 1)
                    self.selected_tile_id = 1
                    self.refresh_all()
                except Exception as exc:
                    QMessageBox.critical(self, "Load Tileset", str(exc))
                    return
            elif lower.endswith(".json"):
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
        if key == Qt.Key.Key_G:
            self.act_grid.setChecked(not self.act_grid.isChecked())
            self.toggle_grid()
            return
        if key == Qt.Key.Key_E:
            self.set_tool(Tool.ERASE)
            return
        if key == Qt.Key.Key_B:
            self.set_tool(Tool.RECTANGLE)
            return
        if key == Qt.Key.Key_F:
            self.set_tool(Tool.FILL)
            return
        if key == Qt.Key.Key_I:
            self.set_tool(Tool.SINGLE)
            return
        if key == Qt.Key.Key_R:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.reset_zoom()
            else:
                self.selected_transform.rotation = (self.selected_transform.rotation + 1) % 4
                self.refresh_all()
            return
        if key == Qt.Key.Key_H:
            self.selected_transform.hflip = not self.selected_transform.hflip
            self.refresh_all()
            return
        if key == Qt.Key.Key_V:
            self.selected_transform.vflip = not self.selected_transform.vflip
            self.refresh_all()
            return
        if key == Qt.Key.Key_Space:
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        super().keyReleaseEvent(event)

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
