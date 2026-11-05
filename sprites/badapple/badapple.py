import json
import os
import time

import numpy as np
import pygame

from sprites.object_state import StateSerializable

W, H = 320, 184
FW, FH = 160, 92
FLOOR = 6
DARK_LIMIT = 0.6

_current_sound = {"s": None}


class badapple(StateSerializable):
    def __init__(self, world_loader=None):
        StateSerializable.__init__(self)
        self.object_type = "badapple"
        self.world_loader = world_loader
        self.world_x = W // 2
        self.world_y = H // 2
        self.pos = [self.world_x, self.world_y]

        base = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "worlds", "16")
        )
        self.frames = np.load(os.path.join(base, "badapple.npy"))
        with open(os.path.join(base, "badapple.json"), "r") as f:
            self.fps = json.load(f)["fps"]

        self.sound = None
        wav = os.path.join(base, "badapple.wav")
        if os.path.exists(wav):
            try:
                self.sound = pygame.mixer.Sound(wav)
            except Exception:
                self.sound = None

        self.floor_mask = pygame.Mask((W, FLOOR), fill=True)
        self.surface = pygame.Surface((W, H))
        self.t0 = None
        self.last_index = -1

    def serialize_state(self):
        return {}

    def deserialize_state(self, state):
        pass

    def _play(self):
        if _current_sound["s"] is not None:
            try:
                _current_sound["s"].stop()
            except Exception:
                pass
        if self.sound is None:
            return
        volume = 0.5
        try:
            volume = self.world_loader.settings.get("master_volume", 0.5)
        except Exception:
            pass
        self.sound.set_volume(volume)
        self.sound.play()
        _current_sound["s"] = self.sound

    def on_unload(self):
        if self.sound is not None:
            try:
                self.sound.stop()
            except Exception:
                pass

    def _build(self, index):
        bits = np.unpackbits(self.frames[index])[: FW * FH].reshape(FH, FW)
        rgb = np.repeat((bits * 255).astype(np.uint8)[:, :, None], 3, axis=2)
        small = pygame.image.frombuffer(rgb.tobytes(), (FW, FH), "RGB")
        self.surface = pygame.transform.scale(small, (W, H))

        if 1.0 - bits.mean() > DARK_LIMIT:
            mask = pygame.Mask((W, H))
        else:
            mask = pygame.mask.from_threshold(
                self.surface, (0, 0, 0, 255), (30, 30, 30, 255)
            )
        mask.draw(self.floor_mask, (0, H - FLOOR))
        pygame.draw.rect(self.surface, (90, 90, 90), (0, H - FLOOR, W, FLOOR))

        if self.world_loader is not None:
            self.world_loader.collision_mask = mask

    def draw_in_world(self, surface, cam_x, cam_y):
        now = time.perf_counter()
        if self.t0 is None:
            self.t0 = now
            self._play()

        index = int((now - self.t0) * self.fps)
        if index >= len(self.frames):
            self.t0 = now
            index = 0
            self.last_index = -1
            self._play()

        if index != self.last_index:
            self._build(index)
            self.last_index = index

        surface.blit(self.surface, (-int(cam_x), -int(cam_y)))
