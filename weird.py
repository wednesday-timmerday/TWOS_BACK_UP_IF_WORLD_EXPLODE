"""
main.py  —  Pygame window, C++ OpenGL renderer

Linux build:
    g++ -shared -fPIC -o renderer.so renderer.cpp -lGL -lX11

Windows build:
    g++ -shared -o renderer.dll renderer.cpp -lopengl32 -lgdi32
"""

import sys
import ctypes
import time
import pygame

# ── load the shared library ──────────────────────────────────────────────────
import platform

if platform.system() == "Windows":
    lib = ctypes.CDLL("./renderer.dll")
else:
    lib = ctypes.CDLL("./renderer.so")

# tell ctypes the return / arg types
lib.render_frame.argtypes  = [ctypes.c_float]
lib.render_frame.restype   = None
lib.set_viewport.argtypes  = [ctypes.c_int, ctypes.c_int]
lib.set_viewport.restype   = None

if platform.system() == "Windows":
    lib.init_gl.argtypes = [ctypes.c_void_p]
    lib.init_gl.restype  = ctypes.c_int
else:
    lib.init_gl.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    lib.init_gl.restype  = ctypes.c_int

# ── pygame init ──────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 800, 600

# IMPORTANT: tell SDL2 not to create its own GL context — we do it in C++
import os
os.environ["SDL_VIDEO_X11_FORCE_EGL"] = "0"   # ensure GLX on Linux

pygame.init()

# Use NOFRAME so SDL doesn't fight with our GL context
# RESIZABLE is fine too
screen = pygame.display.set_mode(
    (WIDTH, HEIGHT),
    pygame.NOFRAME          # or pygame.RESIZABLE
)
pygame.display.set_caption("Pygame window → C++ OpenGL")

# ── hand the window to C++ ───────────────────────────────────────────────────
wm = pygame.display.get_wm_info()

if platform.system() == "Windows":
    hwnd = wm["window"]
    ok   = lib.init_gl(ctypes.c_void_p(hwnd))
else:
    # X11: need both the Display* and the Window XID
    x11_display = wm["display"]   # pointer (int on 64-bit)
    x11_window  = wm["window"]    # XID (unsigned long)
    ok = lib.init_gl(ctypes.c_void_p(x11_display), ctypes.c_ulong(x11_window))

if not ok:
    print("ERROR: C++ failed to create OpenGL context")
    sys.exit(1)

lib.set_viewport(WIDTH, HEIGHT)
print("OpenGL context created by C++  ✓")

# ── main loop ────────────────────────────────────────────────────────────────
clock    = pygame.time.Clock()
prev     = time.perf_counter()

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            running = False

    now = time.perf_counter()
    dt  = now - prev
    prev = now

    # ← entire 3-D render happens in C++
    lib.render_frame(ctypes.c_float(dt))

    # pygame is only used for events + window management here
    # (no pygame.display.flip() — C++ calls SwapBuffers itself)
    clock.tick(0)   # uncapped, print FPS
    fps = clock.get_fps()
    pygame.display.set_caption(f"C++ OpenGL renderer  |  {fps:.0f} FPS")

pygame.quit()