import pygame
import os
import random
import math
import time
import sys
import numpy as np

from assetsLoader import Loader
from ui.textengine.textengine import TextEngine
from sprites.save.save import SaveOBJ


import unicodedata
import string

def clean_text(text):
    # 1. Normalize accents away
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    
    # 2. Remove punctuation
    text = text.translate(str.maketrans('', '', string.punctuation))
    
    # 3. Uppercase everything
    text = text.upper()
    
    return text


class TobyRadiationFox:
    def __init__(self):

        pygame.mixer.init()
        # --- Icon ---
        self.icon_loader = Loader("ui/tobytank")
        self.icon_path = self.icon_loader.load("icoIfTobyTank.png")

        # --- Text engine ---
        self.text_engine_loader = Loader("ui/textengine")
        self.text_engine = TextEngine(self.text_engine_loader.load("tobytank.ttf"))
        self.text_engine.start_text(
            "^special^shake2NOTHING IS LEFT, YOU KILLED THEM ALL&"
            f"ARE YOU PROUD OF YOURSELF?&{clean_text(os.getlogin())}",
            "potato"
        )
        self.text_engine.typing_speed = 13

        self.clock = pygame.time.Clock()

        self.faces = []
        for i in range(1, 3):
            try:
                img = pygame.image.load(self.icon_loader.load(f"{i}.png")).convert_alpha()
                img = pygame.transform.smoothscale(img, (img.get_width() // 4, img.get_height() // 4))
            except Exception:
                img = pygame.image.load(self.icon_loader.load(f"{i}.png")).convert()
                img = pygame.transform.smoothscale(img, (img.get_width() // 4, img.get_height() // 4))
            self.faces.append(img)
        
        print(self.faces)
        # --- CRT / glitch state ---
        self._elapsed = 0.0
        self._glitch = 0.0
        self._next_hit = random.uniform(1.5, 4.0)
        self._band_y = 0.0
        self._static_seed = 0

        # --- caches ---
        self._vignette_cache = {}
        self._last_screen_size = None

        # --- crash ---
        self.crash_path = self.icon_loader.load("CRASH.mp3")
        self.crash_sfx = pygame.mixer.Sound(self.crash_path)

    # ------------------------------------------------------------------
    def check_file(self, filename):
        saveobj = SaveOBJ()
        saveobj.load_save()
        file_loader = Loader("ui")
        file_path = file_loader.load(filename)
        return os.path.exists(file_path)

    # ------------------------------------------------------------------
    def _update_glitch(self, dt):
        self._elapsed += dt
        self._next_hit -= dt

        # occasional spike
        if self._next_hit <= 0:
            self._glitch = 1.0
            self._next_hit = random.uniform(2.0, 6.0)

        # smooth decay so it does not stay permanently at max chaos
        self._glitch = max(0.0, self._glitch - dt * 1.5)

        # soft pulse to keep movement alive
        pulse = (math.sin(self._elapsed * 2.0) + 1.0) * 0.5
        self._glitch = max(self._glitch, pulse * 0.18)

        # rolling band
        self._band_y = (self._band_y + dt * (0.18 + self._glitch * 0.95)) % 1.0
        self._static_seed += 1

    # ------------------------------------------------------------------
    def _tv_static(self, screen):
        w, h = screen.get_size()

        for _ in range(120):  # ~2 seconds at 60 FPS
            # generate random noise
            noise = np.random.randint(0, 256, (w, h, 3), dtype=np.uint8)

            # convert to surface
            surf = pygame.surfarray.make_surface(noise)

            # optional: slight flicker brightness
            flicker = random.uniform(0.6, 1.2)
            surf.fill((int(255*flicker),)*3, special_flags=pygame.BLEND_RGB_MULT)

            screen.blit(surf, (0, 0))
            pygame.display.flip()

            pygame.time.delay(16)

    # ------------------------------------------------------------------
    def _get_vignette(self, w, h):
        key = (w, h)
        if key in self._vignette_cache:
            return self._vignette_cache[key]

        yy, xx = np.mgrid[0:w, 0:h]
        cx = (w - 1) / 2.0
        cy = (h - 1) / 2.0
        max_dist = math.sqrt(cx * cx + cy * cy)

        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        vignette = 1.0 - (dist / max_dist) ** 2
        vignette = np.clip(vignette, 0.55, 1.0).astype(np.float32)

        self._vignette_cache[key] = vignette
        return vignette

    # ------------------------------------------------------------------
    def _apply_crt(self, surf: pygame.Surface) -> pygame.Surface:
        """
        Fast NumPy-based CRT/glitch pass:
          - downscale first
          - NumPy noise / tears / blocks
          - red-channel shift
          - scanlines
          - vignette
          - upscale back
          - cheap alpha band overlay
        """
        w, h = surf.get_size()
        g = self._glitch

        # --- downscale for speed ---
        scale = 2
        sw = max(1, w // scale)
        sh = max(1, h // scale)
        small = pygame.transform.smoothscale(surf, (sw, sh))

        # --- direct view into pixels (no full copy) ---
        arr = pygame.surfarray.pixels3d(small)  # shape: (sw, sh, 3)

        # 1) soft noise
        noise_max = int(6 + g * 26)
        if noise_max > 0:
            noise = np.random.randint(0, noise_max, arr.shape, dtype=np.uint8)
            tmp = arr.astype(np.uint16) + noise.astype(np.uint16)
            np.clip(tmp, 0, 255, out=tmp)
            arr[:] = tmp.astype(np.uint8)

        # 2) horizontal tears (fast, few slices)
        num_tears = int(3 + g * 10)
        max_shift = int(4 + g * 10)
        for _ in range(num_tears):
            if sh < 2:
                break
            y = np.random.randint(0, sh - 1)
            height = np.random.randint(1, min(4, sh - y) + 1)
            shift = np.random.randint(-max_shift, max_shift + 1)
            arr[:, y:y + height] = np.roll(arr[:, y:y + height], shift, axis=0)

        # 3) red-channel chromatic shift
        red_shift = int(1 + g * 3)
        if red_shift > 0:
            arr[:, :, 0] = np.roll(arr[:, :, 0], red_shift, axis=0)

        # 4) scanlines
        scan_factor = 0.78 - g * 0.18
        scan_factor = max(0.45, scan_factor)
        arr[:, ::3] = (arr[:, ::3].astype(np.float32) * scan_factor).astype(np.uint8)

        # 5) vignette
        vignette = self._get_vignette(sw, sh)
        arr[:] = (arr.astype(np.float32) * vignette[:, :, None]).astype(np.uint8)

        # unlock before reusing surface
        del arr

        # upscale back to screen size
        out = pygame.transform.smoothscale(small, (w, h))

        # 7) rolling flash band overlay
        if g > 0.01:
            band_y = int(self._band_y * h)
            band_h = max(3, int(h * (0.03 + g * 0.04)))
            flash_alpha = int(35 + g * 85)

            flash = pygame.Surface((w, band_h), pygame.SRCALPHA)
            flash.fill((255, 255, 255, flash_alpha))
            out.blit(flash, (0, band_y - band_h // 2))

            line = pygame.Surface((w, 2), pygame.SRCALPHA)
            line.fill((200, 220, 255, int(70 + g * 110)))
            out.blit(line, (0, band_y))

        return out

    # ------------------------------------------------------------------
    def draw(self, screen: pygame.Surface):
        running = not self.check_file("tobytank.png")

        if running:
            pygame.display.set_caption("Toby Radiation fox")
            try:
                pygame.display.set_icon(
                    pygame.image.load(self.icon_path).convert_alpha()
                )
            except Exception:
                try:
                    pygame.display.set_icon(pygame.image.load(self.icon_path))
                except Exception:
                    pass

        w, h = screen.get_size()
        game_surf = pygame.Surface((w, h)).convert()

        while running:
            dt = self.clock.tick(60) / 1000.0

            game_surf.fill((0, 0, 0))

            self.text_engine.update(dt)
            self.text_engine.draw(
                200, 400,
                text_color=(255, 255, 255),
                surface=game_surf
            )

            #Face animation
            face_index = int((time.time() * 2) % len(self.faces))
            face_img = self.faces[face_index]
            fx = (w - face_img.get_width()) // 2
            fy = (h - face_img.get_height()) // 2 - 150
            game_surf.blit(face_img, (fx, fy))

            # self._update_glitch(dt)
            # shaded = self._apply_crt(game_surf)

            screen.blit(game_surf, (0, 0))
            pygame.display.flip()

            if self.text_engine.finished:
                self.crash_sfx.play()
                pygame.time.wait(6000)
                sys.exit()