# ThreeDee_engine/ThreeDee.py
#
# C++ renders into a private offscreen FBO â€” completely separate from SDL.
# get_frame_surface() returns a pygame Surface you blit normally.
# SDL owns all window flipping. No fighting, no flicker.

import ctypes
import os
import platform
from pathlib import Path

import pygame


def _find_lib() -> str:
    suffix = ".dll" if platform.system() == "Windows" else ".so"
    name   = "threedee_renderer" + suffix
    here   = Path(__file__).resolve().parent
    for candidate in [here / name, here.parent / name, Path.cwd() / name]:
        if candidate.exists():
            return str(candidate)
    return str(here / name)


_lib_path = _find_lib()
try:
    _lib = ctypes.CDLL(_lib_path)
except OSError as e:
    raise RuntimeError(
        f"[ThreeDee] Could not load renderer library:\n  {_lib_path}\n  {e}\n\n"
        "Build with:\n"
        "  Linux:   g++ -std=c++17 -shared -fPIC -O2 -o threedee_renderer.so threedee_renderer.cpp -lGL -lX11\n"
        "  Windows: g++ -std=c++17 -shared -O2 -static -static-libgcc -static-libstdc++ "
        "-o threedee_renderer.dll threedee_renderer.cpp -lopengl32 -lgdi32"
    )

_lib.init_renderer.argtypes = [ctypes.c_int, ctypes.c_int]
_lib.init_renderer.restype  = ctypes.c_int

_lib.set_viewport.argtypes  = [ctypes.c_int, ctypes.c_int]
_lib.set_viewport.restype   = None

_lib.load_obj.argtypes = [
    ctypes.c_char_p,
    ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
    ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
    ctypes.c_float,
]
_lib.load_obj.restype = ctypes.c_int

_lib.update.argtypes = [ctypes.c_float, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
_lib.update.restype  = None

_lib.render_frame.argtypes     = [ctypes.c_float]
_lib.render_frame.restype      = None

_lib.get_frame_rgba.argtypes   = []
_lib.get_frame_rgba.restype    = ctypes.POINTER(ctypes.c_uint8)

_lib.get_frame_width.argtypes  = []
_lib.get_frame_width.restype   = ctypes.c_int

_lib.get_frame_height.argtypes = []
_lib.get_frame_height.restype  = ctypes.c_int

_lib.shutdown.argtypes = []
_lib.shutdown.restype  = None


class ThreeDeeEngine:
    """
    C++ renders offscreen into an FBO.
    Call draw() each frame to get a pygame Surface, then blit it yourself.
    SDL does the final flip â€” no fighting, no flicker.
    """

    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.width  = screen.get_width()
        self.height = screen.get_height()
        self.player_x: float = 0.0
        self.player_z: float = 0.0

        ok = _lib.init_renderer(self.width, self.height)
        if not ok:
            raise RuntimeError("[ThreeDee] C++ failed to init offscreen renderer")
        print(f"[ThreeDee] offscreen renderer ready ({self.width}Ã—{self.height})")

    def resize(self, width: int, height: int):
        self.width  = int(width)
        self.height = int(height)
        _lib.set_viewport(self.width, self.height)

    def load_obj(self, filename: str, scale: float = 5.0, pos: tuple = (0,0,0),
                 angle: float = 0.0, color: tuple = (200,200,200), spin_speed: float = 0.03):
        filename = os.path.abspath(filename)
        r, g, b  = color
        ok = _lib.load_obj(
            filename.encode("utf-8"),
            ctypes.c_float(scale),
            ctypes.c_float(pos[0]), ctypes.c_float(pos[1]), ctypes.c_float(pos[2]),
            ctypes.c_float(angle),
            ctypes.c_float(float(r)), ctypes.c_float(float(g)), ctypes.c_float(float(b)),
            ctypes.c_float(float(spin_speed)),
        )
        if not ok:
            raise ValueError(f"[ThreeDee] Failed to load OBJ: {filename}")

    def update(self, dt: float, keys):
        w = int(keys[pygame.K_w])
        s = int(keys[pygame.K_s])
        a = int(keys[pygame.K_a])
        d = int(keys[pygame.K_d])
        _lib.update(ctypes.c_float(float(dt)),
                    ctypes.c_int(w), ctypes.c_int(s),
                    ctypes.c_int(a), ctypes.c_int(d))
        speed = 10.0
        if w: self.player_z -= speed * dt
        if s: self.player_z += speed * dt
        if a: self.player_x -= speed * dt
        if d: self.player_x += speed * dt

    def draw(self, dt: float = 0.016) -> pygame.Surface:
        """
        Renders the 3D scene and returns a pygame Surface.
        Blit this to your screen surface, then let SDL flip normally.

        Usage in fight.py draw_text():
            surf = self.threeD_engine.draw()
            screen.blit(surf, (0, 0))
            # then main loop calls pygame.display.flip() as usual
        """
        _lib.render_frame(ctypes.c_float(float(dt)))

        w = int(_lib.get_frame_width())
        h = int(_lib.get_frame_height())
        ptr = _lib.get_frame_rgba()
        if not ptr:
            raise RuntimeError("[ThreeDee] No frame data")

        raw  = ctypes.string_at(ptr, w * h * 4)
        surf = pygame.image.frombuffer(raw, (w, h), "RGBA")
        # OpenGL writes bottom-up, flip vertically
        return pygame.transform.flip(surf, False, True)

    def shutdown(self):
        _lib.shutdown()

    def __del__(self):
        try:
            _lib.shutdown()
        except Exception:
            pass
