import json
import os
import time

class RuntimeJSON:
    def __init__(self, filename, reload_interval=0.5):
        self.filename = filename
        self.reload_interval = reload_interval
        self.last_check = 0
        self.last_mtime = 0
        self.data = {}

        self.load(force=True)

    def load(self, force=False):
        now = time.time()
        if not force and now - self.last_check < self.reload_interval:
            return

        self.last_check = now

        if not os.path.exists(self.filename):
            return

        try:
            mtime = os.path.getmtime(self.filename)
            if mtime != self.last_mtime:
                with open(self.filename, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                self.last_mtime = mtime
                print("[CONFIG] Reloaded", self.filename)
        except Exception as e:
            print("[CONFIG] Failed to reload:", e)

    def get(self, path, default=None):
        ref = self.data
        for key in path:
            if not isinstance(ref, dict) or key not in ref:
                return default
            ref = ref[key]
        return ref
