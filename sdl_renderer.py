"""
sdl_renderer.py  â€”  Drop-in SDL2 renderer for The Weight of Shadows
Replaces the pygame display / draw backend used in main.py and DrawWorld.py.

Requires: pysdl2  (pip install pysdl2 pysdl2-dll)
          Pillow   (pip install Pillow)   â† for image loading fallback
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
import threading
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# SDL2 bootstrap
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

try:
    import sdl2
    import sdl2.ext
    import sdl2.sdlimage as sdlimage
    import sdl2.sdlttf   as sdlttf
except ImportError:
    raise ImportError(
        "pysdl2 is required.  Run:  pip install pysdl2 pysdl2-dll"
    )

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Tiny colour helper  (r, g, b[, a=255])
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class Color:
    __slots__ = ("r", "g", "b", "a")

    def __init__(self, r: int, g: int, b: int, a: int = 255):
        self.r = r; self.g = g; self.b = b; self.a = a

    def __iter__(self):
        return iter((self.r, self.g, self.b, self.a))

    def sdl(self) -> sdl2.SDL_Color:
        c = sdl2.SDL_Color()
        c.r, c.g, c.b, c.a = self.r, self.g, self.b, self.a
        return c

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Camera
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class Camera:
    def __init__(self, x: float = 0, y: float = 0, scale: float = 1.0):
        self.x     = x
        self.y     = y
        self.scale = scale

    def world_to_screen(self, wx: float, wy: float,
                        win_w: int, win_h: int) -> Tuple[float, float]:
        sx = (wx - self.x) * self.scale + win_w  * 0.5
        sy = (wy - self.y) * self.scale + win_h * 0.5
        return sx, sy

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# TextureCache
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TextureCache:
    def __init__(self, renderer):
        self._ren: ctypes.c_void_p = renderer
        self._cache: Dict[Any, ctypes.c_void_p] = {}

    # Load from file path
    def load(self, path: str) -> Optional[ctypes.c_void_p]:
        if path in self._cache:
            return self._cache[path]
        tex = sdlimage.IMG_LoadTexture(self._ren, path.encode())
        if not tex:
            print(f"[TextureCache] Failed: {path} â€” {sdlimage.IMG_GetError()}")
            return None
        self._cache[path] = tex
        return tex

    # Upload raw RGBA bytes  (key = arbitrary hashable, dynamic = re-upload each call)
    def upload_rgba(self, key: Any, pixels: bytes,
                    w: int, h: int, dynamic: bool = False) -> Optional[ctypes.c_void_p]:
        if key in self._cache and not dynamic:
            return self._cache[key]

        if key in self._cache and dynamic:
            tex = self._cache[key]
            # streaming update
            locked_pixels = ctypes.c_void_p()
            pitch = ctypes.c_int()
            sdl2.SDL_LockTexture(tex, None,
                                 ctypes.byref(locked_pixels),
                                 ctypes.byref(pitch))
            row_bytes = w * 4
            buf = (ctypes.c_uint8 * (w * h * 4)).from_buffer_copy(pixels)
            ctypes.memmove(locked_pixels, buf, w * h * 4)
            sdl2.SDL_UnlockTexture(tex)
            return tex

        access = (sdl2.SDL_TEXTUREACCESS_STREAMING if dynamic
                  else sdl2.SDL_TEXTUREACCESS_STATIC)
        tex = sdl2.SDL_CreateTexture(
            self._ren, sdl2.SDL_PIXELFORMAT_RGBA32, access, w, h
        )
        if not tex:
            return None
        sdl2.SDL_SetTextureBlendMode(tex, sdl2.SDL_BLENDMODE_BLEND)

        if dynamic:
            locked_pixels = ctypes.c_void_p()
            pitch = ctypes.c_int()
            sdl2.SDL_LockTexture(tex, None,
                                 ctypes.byref(locked_pixels),
                                 ctypes.byref(pitch))
            buf = (ctypes.c_uint8 * len(pixels)).from_buffer_copy(pixels)
            ctypes.memmove(locked_pixels, buf, len(pixels))
            sdl2.SDL_UnlockTexture(tex)
        else:
            buf = (ctypes.c_uint8 * len(pixels)).from_buffer_copy(pixels)
            sdl2.SDL_UpdateTexture(tex, None, buf, w * 4)

        self._cache[key] = tex
        return tex

    def evict(self, key: Any):
        if key in self._cache:
            sdl2.SDL_DestroyTexture(self._cache.pop(key))

    def clear(self):
        for tex in self._cache.values():
            sdl2.SDL_DestroyTexture(tex)
        self._cache.clear()

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# FontCache
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class FontCache:
    def __init__(self):
        self._cache: Dict[Tuple[str, int], ctypes.c_void_p] = {}

    def load(self, path: str, pt: int) -> Optional[ctypes.c_void_p]:
        key = (path, pt)
        if key in self._cache:
            return self._cache[key]
        font = sdlttf.TTF_OpenFont(path.encode(), pt)
        if not font:
            print(f"[FontCache] Failed: {path}@{pt} â€” {sdlttf.TTF_GetError()}")
            return None
        self._cache[key] = font
        return font

    # Try a system font name (best-effort, Windows only for now)
    def load_sysname(self, name: str, pt: int) -> Optional[ctypes.c_void_p]:
        candidates = [
            f"C:/Windows/Fonts/{name}.ttf",
            f"C:/Windows/Fonts/{name.lower()}.ttf",
            f"/usr/share/fonts/truetype/{name.lower()}/{name.lower()}.ttf",
            f"/System/Library/Fonts/{name}.ttf",
        ]
        for p in candidates:
            if os.path.exists(p):
                return self.load(p, pt)
        return None

    def clear(self):
        for f in self._cache.values():
            sdlttf.TTF_CloseFont(f)
        self._cache.clear()

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Renderer
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class Renderer:
    """
    SDL2 renderer  â€”  replaces pygame display in The Weight of Shadows.

    Usage:
        ren = Renderer(1280, 720, "The Weight of Shadows",
                       render_w=320, render_h=180)
        ren.init_timers()

        while ren.poll_events():
            dt = ren.delta_time()
            ren.clear()
            # ... draw calls ...
            ren.present()
            ren.cap_fps(240)
    """

    def __init__(self, win_w: int = 1280, win_h: int = 720,
                 title: str = "The Weight of Shadows",
                 render_w: int = 320, render_h: int = 180,
                 vsync: bool = False, fullscreen: bool = False):

        if sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_AUDIO) != 0:
            raise RuntimeError(f"SDL_Init: {sdl2.SDL_GetError()}")

        if not (sdlimage.IMG_Init(sdlimage.IMG_INIT_PNG | sdlimage.IMG_INIT_JPG)
                & (sdlimage.IMG_INIT_PNG | sdlimage.IMG_INIT_JPG)):
            raise RuntimeError(f"IMG_Init: {sdlimage.IMG_GetError()}")

        if sdlttf.TTF_Init() != 0:
            raise RuntimeError(f"TTF_Init: {sdlttf.TTF_GetError()}")

        self._win_w  = win_w
        self._win_h  = win_h
        self.render_w = render_w
        self.render_h = render_h

        flags = sdl2.SDL_WINDOW_SHOWN | sdl2.SDL_WINDOW_RESIZABLE
        if fullscreen:
            flags |= sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP

        self._window = sdl2.SDL_CreateWindow(
            title.encode(),
            sdl2.SDL_WINDOWPOS_CENTERED, sdl2.SDL_WINDOWPOS_CENTERED,
            win_w, win_h, flags
        )
        if not self._window:
            raise RuntimeError(f"SDL_CreateWindow: {sdl2.SDL_GetError()}")

        ren_flags = sdl2.SDL_RENDERER_ACCELERATED
        if vsync:
            ren_flags |= sdl2.SDL_RENDERER_PRESENTVSYNC

        self._ren = sdl2.SDL_CreateRenderer(self._window, -1, ren_flags)
        if not self._ren:
            raise RuntimeError(f"SDL_CreateRenderer: {sdl2.SDL_GetError()}")

        # Logical size: game always renders at MINI_RESOLUTION, SDL upscales
        sdl2.SDL_RenderSetLogicalSize(self._ren, render_w, render_h)
        sdl2.SDL_SetRenderDrawBlendMode(self._ren, sdl2.SDL_BLENDMODE_BLEND)

        self.textures = TextureCache(self._ren)
        self.fonts    = FontCache()
        self.camera   = Camera()

        self._events: List[sdl2.SDL_Event] = []
        self._frame_count = 0
        self._last_tick   = 0
        self._dt_tick     = 0
        self._shadow_buf: Optional[bytes] = None
        self._target_stack: List = []

    # â”€â”€ Lifecycle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def init_timers(self):
        now = sdl2.SDL_GetTicks()
        self._last_tick = now
        self._dt_tick   = now

    def destroy(self):
        self.textures.clear()
        self.fonts.clear()
        if self._ren:
            sdl2.SDL_DestroyRenderer(self._ren)
            self._ren = None
        if self._window:
            sdl2.SDL_DestroyWindow(self._window)
            self._window = None
        sdlttf.TTF_Quit()
        sdlimage.IMG_Quit()
        sdl2.SDL_Quit()

    def __del__(self):
        try:
            self.destroy()
        except Exception:
            pass

    # â”€â”€ Window helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def set_title(self, title: str):
        sdl2.SDL_SetWindowTitle(self._window, title.encode())

    def set_icon(self, path: str):
        surf = sdlimage.IMG_Load(path.encode())
        if surf:
            sdl2.SDL_SetWindowIcon(self._window, surf)
            sdl2.SDL_FreeSurface(surf)

    def set_fullscreen(self, on: bool):
        sdl2.SDL_SetWindowFullscreen(
            self._window,
            sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP if on else 0
        )

    # â”€â”€ Frame lifecycle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def clear(self, r: int = 0, g: int = 0, b: int = 0, a: int = 255):
        sdl2.SDL_SetRenderDrawColor(self._ren, r, g, b, a)
        sdl2.SDL_RenderClear(self._ren)

    def present(self):
        sdl2.SDL_RenderPresent(self._ren)
        self._frame_count += 1

    @property
    def frame_count(self) -> int:
        return self._frame_count

    # â”€â”€ Events â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def poll_events(self) -> bool:
        """Returns False when the window should close."""
        self._events.clear()
        ev = sdl2.SDL_Event()
        while sdl2.SDL_PollEvent(ctypes.byref(ev)):
            if ev.type == sdl2.SDL_QUIT:
                return False
            if ev.type == sdl2.SDL_WINDOWEVENT:
                if ev.window.event == sdl2.SDL_WINDOWEVENT_RESIZED:
                    self._win_w = ev.window.data1
                    self._win_h = ev.window.data2
            self._events.append(sdl2.SDL_Event(ev))  # copy
        return True

    @property
    def events(self) -> List[sdl2.SDL_Event]:
        return self._events

    # â”€â”€ FPS / timing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def cap_fps(self, target: int):
        if target <= 0:
            return
        frame_ms = 1000 // target
        now      = sdl2.SDL_GetTicks()
        elapsed  = now - self._last_tick
        if elapsed < frame_ms:
            sdl2.SDL_Delay(frame_ms - elapsed)
        self._last_tick = sdl2.SDL_GetTicks()

    def delta_time(self) -> float:
        now = sdl2.SDL_GetTicks()
        dt  = (now - self._dt_tick) / 1000.0
        self._dt_tick = now
        return min(dt, 0.125)

    def get_fps(self) -> float:
        dt = (sdl2.SDL_GetTicks() - self._last_tick)
        return 1000.0 / dt if dt > 0 else 0.0

    # â”€â”€ Draw â€” colour helper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _set_color(self, r: int, g: int, b: int, a: int = 255):
        sdl2.SDL_SetRenderDrawColor(self._ren, r, g, b, a)

    # â”€â”€ Draw â€” primitives (world space) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def fill_rect(self, wx: float, wy: float, ww: float, wh: float,
                  r: int, g: int, b: int, a: int = 255):
        self._set_color(r, g, b, a)
        sx, sy = self.camera.world_to_screen(wx, wy, self.render_w, self.render_h)
        rect = sdl2.SDL_FRect(sx, sy, ww * self.camera.scale, wh * self.camera.scale)
        sdl2.SDL_RenderFillRectF(self._ren, rect)

    def draw_rect(self, wx: float, wy: float, ww: float, wh: float,
                  r: int, g: int, b: int, a: int = 255, thickness: int = 1):
        self._set_color(r, g, b, a)
        sx, sy = self.camera.world_to_screen(wx, wy, self.render_w, self.render_h)
        rect = sdl2.SDL_FRect(sx, sy, ww * self.camera.scale, wh * self.camera.scale)
        for _ in range(thickness):
            sdl2.SDL_RenderDrawRectF(self._ren, rect)
            rect.x += 1; rect.y += 1; rect.w -= 2; rect.h -= 2

    def fill_circle(self, wx: float, wy: float, radius: float,
                    r: int, g: int, b: int, a: int = 255):
        self._set_color(r, g, b, a)
        sx, sy = self.camera.world_to_screen(wx, wy, self.render_w, self.render_h)
        cr = radius * self.camera.scale
        dy = -cr
        while dy <= cr:
            dx = (cr * cr - dy * dy) ** 0.5
            sdl2.SDL_RenderDrawLineF(self._ren, sx - dx, sy + dy, sx + dx, sy + dy)
            dy += 1.0

    def draw_line(self, x1: float, y1: float, x2: float, y2: float,
                  r: int, g: int, b: int, a: int = 255):
        self._set_color(r, g, b, a)
        sdl2.SDL_RenderDrawLineF(self._ren, x1, y1, x2, y2)

    # Screen-space (HUD / UI)
    def fill_rect_screen(self, x: float, y: float, w: float, h: float,
                         r: int, g: int, b: int, a: int = 255):
        self._set_color(r, g, b, a)
        rect = sdl2.SDL_FRect(x, y, w, h)
        sdl2.SDL_RenderFillRectF(self._ren, rect)

    def draw_rect_screen(self, x: float, y: float, w: float, h: float,
                         r: int, g: int, b: int, a: int = 255, thickness: int = 1):
        self._set_color(r, g, b, a)
        rect = sdl2.SDL_FRect(x, y, w, h)
        for _ in range(thickness):
            sdl2.SDL_RenderDrawRectF(self._ren, rect)
            rect.x += 1; rect.y += 1; rect.w -= 2; rect.h -= 2

    # â”€â”€ Draw â€” textures â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def draw_texture(self, tex,
                     wx: float, wy: float,
                     draw_w: float = -1, draw_h: float = -1,
                     angle: float = 0.0,
                     flip: int = sdl2.SDL_FLIP_NONE,
                     tint: Tuple[int, int, int, int] = (255, 255, 255, 255),
                     screen_space: bool = False):
        if not tex:
            return
        tw = ctypes.c_int(); th = ctypes.c_int()
        sdl2.SDL_QueryTexture(tex, None, None, ctypes.byref(tw), ctypes.byref(th))
        fw = float(tw.value) if draw_w < 0 else draw_w
        fh = float(th.value) if draw_h < 0 else draw_h

        if screen_space:
            sx, sy = wx, wy
        else:
            sx, sy = self.camera.world_to_screen(wx, wy, self.render_w, self.render_h)
            fw *= self.camera.scale
            fh *= self.camera.scale

        sdl2.SDL_SetTextureColorMod(tex, tint[0], tint[1], tint[2])
        sdl2.SDL_SetTextureAlphaMod(tex, tint[3])

        dst = sdl2.SDL_FRect(sx, sy, fw, fh)
        if angle != 0.0 or flip != sdl2.SDL_FLIP_NONE:
            center = sdl2.SDL_FPoint(fw * 0.5, fh * 0.5)
            sdl2.SDL_RenderCopyExF(self._ren, tex, None, dst, angle, center, flip)
        else:
            sdl2.SDL_RenderCopyF(self._ren, tex, None, dst)

    def draw_texture_clip(self, tex,
                          src_x: int, src_y: int, src_w: int, src_h: int,
                          wx: float, wy: float,
                          draw_w: float = -1, draw_h: float = -1,
                          angle: float = 0.0,
                          flip: int = sdl2.SDL_FLIP_NONE,
                          tint: Tuple[int, int, int, int] = (255, 255, 255, 255),
                          screen_space: bool = False):
        if not tex:
            return
        fw = float(src_w) if draw_w < 0 else draw_w
        fh = float(src_h) if draw_h < 0 else draw_h

        if screen_space:
            sx, sy = wx, wy
        else:
            sx, sy = self.camera.world_to_screen(wx, wy, self.render_w, self.render_h)
            fw *= self.camera.scale
            fh *= self.camera.scale

        sdl2.SDL_SetTextureColorMod(tex, tint[0], tint[1], tint[2])
        sdl2.SDL_SetTextureAlphaMod(tex, tint[3])

        src = sdl2.SDL_Rect(src_x, src_y, src_w, src_h)
        dst = sdl2.SDL_FRect(sx, sy, fw, fh)
        if angle != 0.0 or flip != sdl2.SDL_FLIP_NONE:
            center = sdl2.SDL_FPoint(fw * 0.5, fh * 0.5)
            sdl2.SDL_RenderCopyExF(self._ren, tex, src, dst, angle, center, flip)
        else:
            sdl2.SDL_RenderCopyF(self._ren, tex, src, dst)

    # Upload a raw RGBA surface (e.g. from game logic that still uses
    # pygame.Surface internally â€” call pygame.image.tobytes first)
    def blit_surface_data(self, key: Any, rgba_bytes: bytes,
                          w: int, h: int, dynamic: bool = True):
        return self.textures.upload_rgba(key, rgba_bytes, w, h, dynamic)

    # â”€â”€ Draw â€” text â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def draw_text(self, text: str, font_path: str, pt: int,
                  x: float, y: float,
                  r: int = 255, g: int = 255, b: int = 255, a: int = 255):
        font = self.fonts.load(font_path, pt)
        if not font:
            return
        color = sdl2.SDL_Color(r, g, b, a)
        surf  = sdlttf.TTF_RenderUTF8_Blended(font, text.encode(), color)
        if not surf:
            return
        tex = sdl2.SDL_CreateTextureFromSurface(self._ren, surf)
        sdl2.SDL_FreeSurface(surf)
        if not tex:
            return
        tw = ctypes.c_int(); th = ctypes.c_int()
        sdl2.SDL_QueryTexture(tex, None, None, ctypes.byref(tw), ctypes.byref(th))
        dst = sdl2.SDL_FRect(x, y, float(tw.value), float(th.value))
        sdl2.SDL_RenderCopyF(self._ren, tex, None, dst)
        sdl2.SDL_DestroyTexture(tex)

    def draw_text_sysname(self, text: str, name: str, pt: int,
                          x: float, y: float,
                          r: int = 255, g: int = 255, b: int = 255, a: int = 255):
        font = self.fonts.load_sysname(name, pt)
        if not font:
            return
        color = sdl2.SDL_Color(r, g, b, a)
        surf  = sdlttf.TTF_RenderUTF8_Blended(font, text.encode(), color)
        if not surf:
            return
        tex = sdl2.SDL_CreateTextureFromSurface(self._ren, surf)
        sdl2.SDL_FreeSurface(surf)
        if not tex:
            return
        tw = ctypes.c_int(); th = ctypes.c_int()
        sdl2.SDL_QueryTexture(tex, None, None, ctypes.byref(tw), ctypes.byref(th))
        dst = sdl2.SDL_FRect(x, y, float(tw.value), float(th.value))
        sdl2.SDL_RenderCopyF(self._ren, tex, None, dst)
        sdl2.SDL_DestroyTexture(tex)

    # â”€â”€ Shadow / light pass â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def draw_shadow_map(self, alpha_map: bytes, w: int, h: int):
        """
        Render a greyscale shadow/darkness map over the scene.
        alpha_map: bytes of length w*h, each byte = darkness alpha (0=lit, 255=dark)
        Uses SDL_BLENDMODE_MOD so dark pixels multiply the scene colour.
        """
        # Expand 1-channel â†’ RGBA  (r=g=b=0, a=alpha)
        rgba = bytearray(w * h * 4)
        for i in range(w * h):
            rgba[i * 4 + 3] = alpha_map[i]   # r,g,b stay 0

        tex = self.textures.upload_rgba("__shadow_map__", bytes(rgba), w, h, dynamic=True)
        if not tex:
            return
        sdl2.SDL_SetTextureBlendMode(tex, sdl2.SDL_BLENDMODE_MOD)
        sdl2.SDL_SetTextureScaleMode(tex, sdl2.SDL_ScaleModeLinear)
        dst = sdl2.SDL_FRect(0, 0, float(self.render_w), float(self.render_h))
        sdl2.SDL_RenderCopyF(self._ren, tex, None, dst)

    def draw_light(self, wx: float, wy: float, radius: float,
                   r: int = 255, g: int = 200, b: int = 100, a: int = 180):
        """
        Additive radial light at world position.
        Multiple lights stack correctly.
        """
        sx, sy = self.camera.world_to_screen(wx, wy, self.render_w, self.render_h)
        cr = radius * self.camera.scale
        sdl2.SDL_SetRenderDrawBlendMode(self._ren, sdl2.SDL_BLENDMODE_ADD)
        steps = 8
        for i in range(steps, -1, -1):
            frac = i / steps
            aa   = int(a * frac * frac)
            self._set_color(r, g, b, aa)
            step_r = cr * frac
            dy = -step_r
            while dy <= step_r:
                dx = max(0.0, step_r * step_r - dy * dy) ** 0.5
                sdl2.SDL_RenderDrawLineF(self._ren, sx - dx, sy + dy, sx + dx, sy + dy)
                dy += 1.0
        sdl2.SDL_SetRenderDrawBlendMode(self._ren, sdl2.SDL_BLENDMODE_BLEND)

    # â”€â”€ Render targets (off-screen) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def create_render_target(self, w: int, h: int):
        tex = sdl2.SDL_CreateTexture(
            self._ren, sdl2.SDL_PIXELFORMAT_RGBA32,
            sdl2.SDL_TEXTUREACCESS_TARGET, w, h
        )
        sdl2.SDL_SetTextureBlendMode(tex, sdl2.SDL_BLENDMODE_BLEND)
        return tex

    def push_render_target(self, target):
        self._target_stack.append(sdl2.SDL_GetRenderTarget(self._ren))
        sdl2.SDL_SetRenderTarget(self._ren, target)

    def pop_render_target(self):
        if self._target_stack:
            sdl2.SDL_SetRenderTarget(self._ren, self._target_stack.pop())

    # â”€â”€ Key / mouse state helpers  â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @staticmethod
    def get_keys() -> ctypes.Array:
        """Returns SDL keyboard state array. Index with sdl2.SDL_SCANCODE_*."""
        num = ctypes.c_int()
        return sdl2.SDL_GetKeyboardState(ctypes.byref(num))

    @staticmethod
    def get_mouse_pos() -> Tuple[int, int]:
        x = ctypes.c_int(); y = ctypes.c_int()
        sdl2.SDL_GetMouseState(ctypes.byref(x), ctypes.byref(y))
        return x.value, y.value

    @staticmethod
    def get_mouse_buttons() -> int:
        return sdl2.SDL_GetMouseState(None, None)

    # â”€â”€ Internal SDL handles (for interop) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @property
    def sdl_renderer(self):
        return self._ren

    @property
    def sdl_window(self):
        return self._window


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Convenience: blit a pygame Surface â†’ SDL texture
# (used during the pygameâ†’SDL migration; remove once all surfaces are native)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def pygame_surface_to_sdl_texture(renderer: Renderer, surface, key: str,
                                   dynamic: bool = False):
    """
    Convert a pygame.Surface to an SDL texture stored in renderer.textures.
    Requires pygame to be importable (only used during transition).
    """
    import pygame
    w, h = surface.get_size()
    raw = pygame.image.tobytes(surface, "RGBA", False)
    return renderer.textures.upload_rgba(key, raw, w, h, dynamic=dynamic)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Quick smoke-test
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

if __name__ == "__main__":
    import math

    ren = Renderer(1280, 720, "shadow_rendering_lib â€” Python SDL2 Renderer",
                   render_w=320, render_h=180)
    ren.init_timers()

    angle = 0.0
    while ren.poll_events():
        dt = ren.delta_time()

        ren.clear(20, 35, 41)

        # Background
        ren.fill_rect_screen(0, 0, 320, 180, 10, 18, 22)

        # Bouncing circle
        cx = 160.0 + math.cos(angle) * 40.0
        cy =  90.0 + math.sin(angle) * 25.0
        ren.fill_circle(cx, cy, 8, 255, 200, 80, 200)
        ren.draw_light(cx, cy, 40.0, 255, 180, 60, 160)

        # Vignette shadow map
        smap = bytearray(320 * 180)
        for y in range(180):
            for x in range(320):
                dx = (x - 160) / 160.0
                dy = (y - 90)  / 90.0
                d  = min(1.0, dx * dx + dy * dy)
                smap[y * 320 + x] = int(d * 200)
        ren.draw_shadow_map(bytes(smap), 320, 180)

        ren.present()
        ren.cap_fps(240)

        angle += dt * 1.5

    ren.destroy()

