import pygame
from assetsLoader import Loader
from collections import OrderedDict

class EnemyBase:
    _frame_cache = OrderedDict()
    _mini_cache = {}
    _puzzle_cache = {}
    _atlas_cache = OrderedDict()

    # Max entries for main frame/atlas caches to avoid unbounded memory growth
    _FRAME_CACHE_MAX = 200

    @classmethod
    def _cache_insert(cls, cache, key, value):
        try:
            cache[key] = value
            # move to end (most recently used)
            if isinstance(cache, OrderedDict):
                cache.move_to_end(key, last=True)
            # evict oldest when exceeding limit
            if cache is cls._frame_cache and len(cache) > cls._FRAME_CACHE_MAX:
                try:
                    cache.popitem(last=False)
                except Exception:
                    pass
        except Exception:
            cache[key] = value

    def __init__(self, name, frame_count=1, scale_percentage=(100, 100),
                 mini_scale_percentage=(50, 50), max_puzzles=5, puzzle_size=(64, 64)):

        self.name = name
        self.frame_count = frame_count
        self.current_frame = 0
        self.scale_percentage_mini = mini_scale_percentage
        self.loader = Loader(f"sprites/{name.lower()}")
        self.current_attack = 1
        
        # Animation frame tracking
        self.last_frame_update = 0
        self.frame_update_interval = 100  # ms between frame updates

        # --------------- MAIN FRAMES ---------------
        key_main = (name, frame_count)
        if key_main not in EnemyBase._frame_cache:
            frames = []
            for i in range(1, frame_count + 1):
                path = self.loader.load(f"frames/{name.lower()}-{i}.png")
                img = pygame.image.load(path).convert_alpha()

                new_w = int(img.get_width() * (scale_percentage[0] / 100))
                new_h = int(img.get_height() * (scale_percentage[1] / 100))
                img = pygame.transform.scale(img, (new_w, new_h))
                frames.append(img)

            EnemyBase._cache_insert(EnemyBase._frame_cache, key_main, frames)

        self.frames = EnemyBase._frame_cache[key_main]

        # Build or reuse a sprit atlas for the frames (helps batching)
        try:
            from sprite_atlas import build_atlas
            if key_main not in EnemyBase._atlas_cache:
                atlas, rects = build_atlas(self.frames)
                EnemyBase._cache_insert(EnemyBase._atlas_cache, key_main, (atlas, rects))
            self._atlas, self._atlas_rects = EnemyBase._atlas_cache[key_main]
        except Exception:
            self._atlas = None
            self._atlas_rects = None

        # --------------- MINI FRAMES ---------------
        key_mini = (name, frame_count, mini_scale_percentage)
        if key_mini not in EnemyBase._mini_cache:
            frames_mini = []
            for i in range(1, frame_count + 1):
                path = self.loader.load(f"frames/{name.lower()}-{i}-mini.png")
                img = pygame.image.load(path).convert_alpha()

                new_w = int(img.get_width() * (mini_scale_percentage[0] / 100))
                new_h = int(img.get_height() * (mini_scale_percentage[1] / 100))
                img = pygame.transform.scale(img, (new_w, new_h))
                frames_mini.append(img)

            EnemyBase._mini_cache[key_mini] = frames_mini

        self.mini_frames = EnemyBase._mini_cache[key_mini]

        # --------------- PUZZLES ---------------
        key_puzzles = (name, max_puzzles, puzzle_size)
        if key_puzzles not in EnemyBase._puzzle_cache:
            puzzles = []
            for i in range(1, max_puzzles + 1):
                try:
                    path = self.loader.load(f"puzzles/puzzle-{i}.png")
                    img = pygame.image.load(path).convert_alpha()
                    img = pygame.transform.scale(img, puzzle_size)
                    puzzles.append(img)
                except Exception:
                    continue

            EnemyBase._puzzle_cache[key_puzzles] = puzzles

        self.puzzles = EnemyBase._puzzle_cache[key_puzzles]

        # --------------- Animation & Position ---------------
        self.last_update = pygame.time.get_ticks()
        self.frame_delay = 1000

        self.world_x = 0
        self.world_y = 0
        self.screen_x = 0
        self.screen_y = 0
        self.pos = [0, 0]

        self.rect = self.frames[0].get_rect()

    def blit_frame_from_atlas(self, dst_surface, index, dest_pos, alpha=255):
        """Blit the indexed frame using the shared atlas if available, otherwise fall back."""
        try:
            if self._atlas and self._atlas_rects:
                src_rect = self._atlas_rects[index]
                self._atlas.set_alpha(alpha)
                dst_surface.blit(self._atlas, dest_pos, src_rect)
                self._atlas.set_alpha(255)  # Reset alpha after blitting
                return
        except Exception:
            pass

        # Fallback
        try:
            frame = self.frames[index]
            frame.set_alpha(alpha)
            dst_surface.blit(frame, dest_pos)
            frame.set_alpha(255)  # Reset alpha after blitting
        except Exception:
            pass
