import sys, os

class Loader:
    def __init__(self, base_path):
        self.base_path = base_path
        # In-memory surface cache to avoid reloading/converting each frame
        self._surface_cache = {}

    def get_base_dir(self):
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.abspath(os.path.dirname(__file__))

    def load(self, filename):
        if hasattr(sys, "_MEIPASS"):
            return os.path.join(sys._MEIPASS, self.base_path, filename)
        return os.path.join(self.get_base_dir(), self.base_path, filename)

    def load_surface(self, filename, alpha=True):
        """Load and return a converted pygame Surface. Accepts either a filename
        relative to the loader's base_path or an absolute path.
        """
        import pygame
        # If caller passed a full path, use it directly
        if os.path.isabs(filename) or os.path.sep in filename:
            path = filename
        else:
            path = self.load(filename)

        if not os.path.exists(path):
            raise FileNotFoundError(path)

        cache_key = (os.path.abspath(path), bool(alpha))
        if cache_key in self._surface_cache:
            return self._surface_cache[cache_key]

        surf = pygame.image.load(path)
        try:
            if alpha:
                out = surf.convert_alpha()
            else:
                out = surf.convert()
        except Exception:
            out = surf

        # store converted surface for reuse
        try:
            self._surface_cache[cache_key] = out
        except Exception:
            pass
        return out

    def write(self, filename, data):
        full_path = os.path.join(self.get_base_dir(), self.base_path, filename)
        with open(full_path, "w") as f:
            f.write(data)
        return True



