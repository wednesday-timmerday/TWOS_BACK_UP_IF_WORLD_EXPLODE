"""
GPU Render Helper for Pyglet 2.x
"""

import pyglet
from pyglet.graphics.ordereddrawing import OrderedGroup
import pygame
import time
import typing as t

# ---------------- Utilities ----------------
def surface_to_imagedata(surface: pygame.Surface) -> pyglet.image.ImageData:
    """Convert pygame.Surface to pyglet ImageData (RGBA, Y-flipped)."""
    w, h = surface.get_size()
    raw = pygame.image.tobytes(surface, "RGBA", False)
    return pyglet.image.ImageData(w, h, "RGBA", raw, pitch=-w*4)

# ---------------- Texture Cache ----------------
class TextureEntry:
    def __init__(self, image: pyglet.image.ImageData, dynamic: bool=False):
        self.image = image.get_texture()
        self.dynamic = dynamic

    def update_from_surface(self, surface: pygame.Surface):
        img = surface_to_imagedata(surface)
        self.image = img.get_texture()

class TextureCache:
    def __init__(self):
        self._cache: t.Dict[t.Any, TextureEntry] = {}

    def get_from_surface(self, surface: pygame.Surface, dynamic: bool=False) -> TextureEntry:
        key = id(surface)
        if key not in self._cache:
            self._cache[key] = TextureEntry(surface_to_imagedata(surface), dynamic)
        elif dynamic:
            self._cache[key].update_from_surface(surface)
        return self._cache[key]

    def update_surface(self, surface: pygame.Surface):
        key = id(surface)
        if key in self._cache:
            self._cache[key].update_from_surface(surface)

    def clear(self):
        self._cache.clear()

# ---------------- Sprite Pool ----------------
class SpritePool:
    """Reusable sprites per layer, using pyglet Batch + OrderedGroup."""
    def __init__(self, batch: pyglet.graphics.Batch):
        self.batch = batch
        self._pools: t.Dict[int, t.List[pyglet.sprite.Sprite]] = {}
        self._active_index: t.Dict[int, int] = {}

    def _ensure_layer(self, layer: int):
        if layer not in self._pools:
            self._pools[layer] = []
            self._active_index[layer] = 0

    def acquire(self, image: pyglet.image.Texture, layer: int=0) -> pyglet.sprite.Sprite:
        self._ensure_layer(layer)
        pool = self._pools[layer]
        idx = self._active_index[layer]
        if idx < len(pool):
            spr = pool[idx]
            spr.image = image
        else:
            group = OrderedGroup(layer)
            spr = pyglet.sprite.Sprite(img=image, x=0, y=0, batch=self.batch, group=group)
            pool.append(spr)
        self._active_index[layer] += 1
        return pool[idx]

    def reset_frame(self):
        for layer, pool in self._pools.items():
            active = self._active_index.get(layer, 0)
            for i in range(active, len(pool)):
                pool[i].visible = False
            self._active_index[layer] = 0

# ---------------- Camera ----------------
class Camera:
    def __init__(self, x: float=0, y: float=0, scale: float=1.0):
        self.x = x
        self.y = y
        self.scale = scale

    def world_to_screen(self, wx: float, wy: float, screen_w: int, screen_h: int) -> t.Tuple[float, float]:
        sx = (wx - self.x) * self.scale + screen_w/2
        sy = (wy - self.y) * self.scale + screen_h/2
        return sx, sy

# ---------------- Renderer ----------------
class Renderer:
    def __init__(self, width: int=800, height: int=600, title: str="Renderer",
                 vsync: bool=False, show_fps: bool=True, target_fps: t.Optional[float]=None):
        self.window = pyglet.window.Window(width, height, caption=title, vsync=vsync)
        self.batch = pyglet.graphics.Batch()
        self.texture_cache = TextureCache()
        self.sprite_pool = SpritePool(self.batch)
        self.camera = Camera()
        self.show_fps = show_fps
        self.fps_display = pyglet.window.FPSDisplay(self.window) if show_fps else None
        self.target_fps = target_fps
        self._last_present_time = time.time()
        self._running = False

    # ----- Texture helpers -----
    def texture_from_surface(self, surface: pygame.Surface, dynamic: bool=False) -> TextureEntry:
        return self.texture_cache.get_from_surface(surface, dynamic=dynamic)

    def update_surface_texture(self, surface: pygame.Surface):
        self.texture_cache.update_surface(surface)

    # ----- Draw API -----
    def draw(self, surface_or_key: t.Union[pygame.Surface, TextureEntry, pyglet.image.Texture],
             x: float, y: float, width: t.Optional[float]=None, height: t.Optional[float]=None,
             rotation: float=0.0, scale: float=1.0, layer: int=0,
             anchor: str="center", color: t.Tuple[int,int,int,int]=(255,255,255,255)):
        # resolve texture
        if isinstance(surface_or_key, TextureEntry):
            tex = surface_or_key.image
        elif isinstance(surface_or_key, pyglet.image.Texture):
            tex = surface_or_key
        else:
            tex = self.texture_from_surface(surface_or_key).image

        tex_w, tex_h = tex.width, tex.height
        draw_w = tex_w * (scale if width is None else (width/tex_w))
        draw_h = tex_h * (scale if height is None else (height/tex_h))
        sx, sy = self.camera.world_to_screen(x, y, self.window.width, self.window.height)

        if anchor == "center":
            spr_x = sx - draw_w/2
            spr_y = sy - draw_h/2
        else:  # topleft
            spr_x = sx
            spr_y = sy - draw_h

        spr = self.sprite_pool.acquire(tex, layer=layer)
        spr.visible = True
        spr.x = spr_x
        spr.y = spr_y
        spr.scale_x = draw_w / tex_w
        spr.scale_y = draw_h / tex_h
        spr.rotation = rotation
        spr.color = color[:3]
        spr.opacity = color[3]

    def begin_frame(self):
        self.sprite_pool.reset_frame()

    def end_frame(self):
        self.window.clear()
        self.batch.draw()
        if self.fps_display:
            self.fps_display.draw()
        self.window.flip()

    # ----- Main loop -----
    def run(self, update_cb: t.Optional[t.Callable[[float], None]]=None):
        self._running = True
        try:
            while not self.window.has_exit and self._running:
                dt = pyglet.clock.tick()
                self.window.dispatch_events()
                if update_cb:
                    update_cb(dt)
                self.begin_frame()
                self.end_frame()
                if self.target_fps:
                    target_frame_time = 1.0 / self.target_fps
                    elapsed = time.time() - self._last_present_time
                    to_sleep = target_frame_time - elapsed
                    if to_sleep > 0:
                        time.sleep(to_sleep)
                self._last_present_time = time.time()
        finally:
            pygame.quit()
            self._running = False

    def stop(self):
        self._running = False

# ---------------- Example Usage ----------------
if __name__ == "__main__":
    pygame.init()

    renderer = Renderer(800, 600, "Pyglet 2.x Render Helper", vsync=False, show_fps=True)

    surf = pygame.Surface((128, 128), pygame.SRCALPHA)
    pygame.draw.circle(surf, (255, 60, 60), (64,64), 60)
    tex_entry = renderer.texture_from_surface(surf)

    # state
    angle = 0.0

    def update(dt):
        global angle  # works because update is now nested in main
        angle += 90.0 * dt
        renderer.draw(tex_entry, x=0, y=0, rotation=angle, scale=1.5)

    # Nested main so nonlocal works
    def main():
        global angle
        renderer.run(update_cb=update)

    main()
