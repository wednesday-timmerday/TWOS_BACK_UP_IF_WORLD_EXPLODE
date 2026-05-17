"""
bullet_types.py — Bullet type definitions & registry.

A BulletType describes how a bullet looks and behaves visually.
Pass a BulletType (or its string key) to spawn() / spawn_at_angle() /
spawn_homing() to get different visuals and default properties.

--------------------------------------------------------------------
QUICK USAGE
--------------------------------------------------------------------

    from bulletengine.bullet_types import BulletTypes

    # Use a built-in type by name
    engine.spawn_at_angle(x, y, angle, speed, bullet_type="laser")

    # Use the constant directly (autocomplete-friendly)
    engine.spawn_at_angle(x, y, angle, speed, bullet_type=BulletTypes.ORB)

    # Register a custom type with a sprite image
    BulletTypes.register(
        "my_bullet",
        image_path="sprites/my_bullet.png",
        size=6,
        color=(255, 200, 0),
        rotate_to_velocity=True,
    )

--------------------------------------------------------------------
BUILT-IN TYPES
--------------------------------------------------------------------

    "dot"       — tiny coloured dot (default, fastest to draw)
    "orb"       — glowing soft circle with alpha
    "laser"     — thin elongated needle
    "needle"    — sharp pointed shard
    "star"      — 4-point star shape
    "ring"      — hollow ring / donut
    "crystal"   — angular diamond shape
    "fire"      — animated orange teardrop
    "ice"       — pale blue shard
    "plasma"    — bright neon core + outer glow
    "image"     — use a custom sprite (set image_path)

--------------------------------------------------------------------
"""

import math
import os
from dataclasses import dataclass, field
from typing import Optional, Tuple

try:
    import pygame
    _PYGAME_AVAILABLE = True
except ImportError:
    _PYGAME_AVAILABLE = False


@dataclass
class BulletType:
    """
    Describes the visual properties of a bullet type.

    Attributes:
        key:               Unique string identifier (e.g. "laser").
        color:             Default RGB color tuple used when no override given.
        size:              Default collision radius (pixels).
        image_path:        Optional path to a sprite image file.
        rotate_to_velocity: If True the sprite is rotated to match movement dir.
        glow:              Draw a soft glow behind the bullet (pygame only).
        glow_radius:       Radius of the glow effect in pixels.
        glow_alpha:        Alpha of the glow (0-255).
        shape:             Internal draw-mode used when no image is loaded.
                           One of: "circle", "needle", "star", "ring",
                                   "crystal", "teardrop", "diamond"
        scale:             Multiplier applied on top of per-bullet size.
    """
    key:                str
    color:              Tuple[int, int, int] = (255, 70, 70)
    size:               int                 = 4
    image_path:         Optional[str]       = None
    rotate_to_velocity: bool                = False
    glow:               bool                = False
    glow_radius:        int                 = 8
    glow_alpha:         int                 = 80
    shape:              str                 = "circle"   # fallback draw mode
    scale:              float               = 1.0

    # --- internal cache, not part of public API ---
    _surface:           Optional[object]    = field(default=None, init=False, repr=False, compare=False)
    _surface_loaded:    bool                = field(default=False, init=False, repr=False, compare=False)

    def get_surface(self, size_override: int = 0) -> Optional[object]:
        """
        Return a cached pygame.Surface for this type, loading/scaling on demand.
        Returns None if pygame is not available or no image is set.

        Args:
            size_override: If > 0, scale the image to this pixel diameter.
        """
        if not _PYGAME_AVAILABLE:
            return None
        if not self.image_path:
            return None

        diameter = max(1, (size_override or self.size) * 2)

        if not self._surface_loaded:
            try:
                raw = pygame.image.load(self.image_path).convert_alpha()
                self._surface = pygame.transform.scale(raw, (diameter, diameter))
            except Exception as e:
                print(f"[BulletTypes] Could not load '{self.image_path}': {e}")
                self._surface = None
            self._surface_loaded = True

        return self._surface

    def make_surface(self, size: int) -> Optional[object]:
        """
        Create (or retrieve cached) a pygame.Surface for this bullet at the
        given radius. Handles both image-based and procedural shapes.

        Args:
            size: Bullet collision radius in pixels.
        """
        if not _PYGAME_AVAILABLE:
            return None

        diameter = max(2, int(size * 2 * self.scale))

        if self.image_path:
            return self.get_surface(size)

        # -- procedural shapes --
        surf = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
        cx = cy = diameter // 2
        r = max(1, diameter // 2)
        c = self.color

        if self.shape == "circle":
            pygame.draw.circle(surf, (*c, 220), (cx, cy), r)

        elif self.shape == "ring":
            pygame.draw.circle(surf, (*c, 220), (cx, cy), r, max(1, r // 3))

        elif self.shape == "needle":
            # Thin horizontal line (rotated at draw-time if rotate_to_velocity)
            hw = max(2, diameter)
            hh = max(1, diameter // 5)
            rect = pygame.Rect(0, cy - hh // 2, hw, hh)
            pygame.draw.ellipse(surf, (*c, 230), rect)

        elif self.shape == "star":
            _draw_star(surf, cx, cy, r, 4, c)

        elif self.shape == "crystal":
            _draw_crystal(surf, cx, cy, r, c)

        elif self.shape == "teardrop":
            _draw_teardrop(surf, cx, cy, r, c)

        elif self.shape == "diamond":
            _draw_diamond(surf, cx, cy, r, c)

        else:
            pygame.draw.circle(surf, (*c, 220), (cx, cy), r)

        if self.glow:
            gsurf = pygame.Surface((diameter + self.glow_radius * 2,
                                    diameter + self.glow_radius * 2), pygame.SRCALPHA)
            gr = r + self.glow_radius
            gcx = gcy = gr
            pygame.draw.circle(gsurf, (*c, self.glow_alpha), (gcx, gcy), gr)
            combined = pygame.Surface(gsurf.get_size(), pygame.SRCALPHA)
            combined.blit(gsurf, (0, 0))
            combined.blit(surf, (self.glow_radius, self.glow_radius))
            return combined

        return surf


# ---------------------------------------------------------------------------
# Helper draw functions
# ---------------------------------------------------------------------------

def _draw_star(surf, cx, cy, r, points, color):
    """Draw a N-pointed star."""
    verts = []
    inner = r * 0.45
    for i in range(points * 2):
        angle = math.radians(i * 180 / points - 90)
        radius = r if i % 2 == 0 else inner
        verts.append((cx + math.cos(angle) * radius,
                       cy + math.sin(angle) * radius))
    if len(verts) >= 3:
        pygame.draw.polygon(surf, (*color, 230), verts)


def _draw_crystal(surf, cx, cy, r, color):
    """Draw a hexagonal crystal."""
    verts = []
    for i in range(6):
        angle = math.radians(i * 60 - 90)
        verts.append((cx + math.cos(angle) * r,
                       cy + math.sin(angle) * r))
    if len(verts) >= 3:
        pygame.draw.polygon(surf, (*color, 220), verts)
        pygame.draw.polygon(surf, (255, 255, 255, 80), verts, max(1, r // 6))


def _draw_teardrop(surf, cx, cy, r, color):
    """Draw a teardrop / flame shape (wider at bottom)."""
    pygame.draw.circle(surf, (*color, 230), (cx, cy + r // 3), max(1, r * 2 // 3))
    tip = [(cx, cy - r), (cx - r // 2, cy + r // 3), (cx + r // 2, cy + r // 3)]
    if len(tip) >= 3:
        pygame.draw.polygon(surf, (*color, 230), tip)


def _draw_diamond(surf, cx, cy, r, color):
    """Draw a 4-point diamond."""
    verts = [
        (cx,          cy - r),
        (cx + r // 2, cy),
        (cx,          cy + r),
        (cx - r // 2, cy),
    ]
    pygame.draw.polygon(surf, (*color, 230), verts)
    pygame.draw.polygon(surf, (255, 255, 255, 60), verts, max(1, r // 5))


# ---------------------------------------------------------------------------
# Built-in type definitions
# ---------------------------------------------------------------------------

_BUILTINS: list[BulletType] = [
    BulletType(
        key="dot",
        color=(255, 70, 70),
        size=2,
        shape="circle",
        glow=False,
    ),
    BulletType(
        key="orb",
        color=(255, 120, 120),
        size=5,
        shape="circle",
        glow=True,
        glow_radius=6,
        glow_alpha=70,
    ),
    BulletType(
        key="laser",
        color=(255, 255, 100),
        size=2,
        shape="needle",
        rotate_to_velocity=True,
        scale=2.5,
    ),
    BulletType(
        key="needle",
        color=(200, 255, 200),
        size=3,
        shape="needle",
        rotate_to_velocity=True,
        scale=1.6,
    ),
    BulletType(
        key="star",
        color=(255, 220, 50),
        size=5,
        shape="star",
        glow=True,
        glow_radius=4,
        glow_alpha=60,
    ),
    BulletType(
        key="ring",
        color=(100, 200, 255),
        size=5,
        shape="ring",
    ),
    BulletType(
        key="crystal",
        color=(150, 100, 255),
        size=5,
        shape="crystal",
        glow=True,
        glow_radius=5,
        glow_alpha=55,
    ),
    BulletType(
        key="fire",
        color=(255, 140, 30),
        size=5,
        shape="teardrop",
        rotate_to_velocity=True,
        glow=True,
        glow_radius=6,
        glow_alpha=65,
    ),
    BulletType(
        key="ice",
        color=(180, 230, 255),
        size=4,
        shape="crystal",
        glow=True,
        glow_radius=4,
        glow_alpha=50,
    ),
    BulletType(
        key="plasma",
        color=(200, 50, 255),
        size=4,
        shape="circle",
        glow=True,
        glow_radius=10,
        glow_alpha=90,
    ),
    BulletType(
        key="image",
        color=(255, 255, 255),
        size=4,
        image_path=None,   # set via register() or directly
        rotate_to_velocity=False,
    ),
]


class _BulletTypeRegistry:
    """
    Singleton registry mapping string keys → BulletType objects.

    Attributes (class-level shortcuts):
        DOT, ORB, LASER, NEEDLE, STAR, RING, CRYSTAL, FIRE, ICE, PLASMA, IMAGE
    """

    DOT     = "dot"
    ORB     = "orb"
    LASER   = "laser"
    NEEDLE  = "needle"
    STAR    = "star"
    RING    = "ring"
    CRYSTAL = "crystal"
    FIRE    = "fire"
    ICE     = "ice"
    PLASMA  = "plasma"
    IMAGE   = "image"

    def __init__(self):
        self._registry: dict[str, BulletType] = {}
        for bt in _BUILTINS:
            self._registry[bt.key] = bt

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str) -> BulletType:
        """
        Return BulletType by key. Falls back to "dot" if key not found.

        Args:
            key: String key (e.g. "laser", "orb", "my_custom_bullet").
        """
        bt = self._registry.get(key)
        if bt is None:
            print(f"[BulletTypes] Unknown type '{key}', falling back to 'dot'.")
            bt = self._registry["dot"]
        return bt

    def register(
        self,
        key: str,
        *,
        color:              Tuple[int, int, int] = (255, 70, 70),
        size:               int                  = 4,
        image_path:         Optional[str]         = None,
        rotate_to_velocity: bool                  = False,
        glow:               bool                  = False,
        glow_radius:        int                   = 8,
        glow_alpha:         int                   = 80,
        shape:              str                   = "circle",
        scale:              float                 = 1.0,
    ) -> BulletType:
        """
        Register a new bullet type (or overwrite an existing one).

        Args:
            key:               Unique identifier string.
            color:             Default RGB color.
            size:              Default collision radius.
            image_path:        Path to sprite PNG (optional).
            rotate_to_velocity: Rotate sprite toward movement direction.
            glow:              Draw glow halo.
            glow_radius:       Glow halo size (pixels).
            glow_alpha:        Glow transparency (0=invisible, 255=opaque).
            shape:             Procedural shape if no image_path set.
                               Options: "circle", "needle", "star", "ring",
                                        "crystal", "teardrop", "diamond"
            scale:             Scale multiplier on top of per-bullet size.

        Returns:
            The newly registered BulletType.

        Example::

            BulletTypes.register(
                "boss_bullet",
                image_path="sprites/boss_bullet.png",
                size=8,
                rotate_to_velocity=True,
                glow=True,
            )
        """
        print("...---...")
        bt = BulletType(
            key=key,
            color=color,
            size=size,
            image_path=image_path,
            rotate_to_velocity=rotate_to_velocity,
            glow=glow,
            glow_radius=glow_radius,
            glow_alpha=glow_alpha,
            shape=shape,
            scale=scale,
        ) # = None
        self._registry[key] = bt
        return bt #Returns none?!?!? WHY TF DOES IT RETURN NONE

    def list_types(self) -> list[str]:
        """Return a list of all registered type keys."""
        return sorted(self._registry.keys())

    def __contains__(self, key: str) -> bool:
        return key in self._registry

    def __getitem__(self, key: str) -> BulletType:
        return self.get(key)


# Module-level singleton — import this everywhere
BulletTypes = _BulletTypeRegistry()
