from sprites.base_enemy import EnemyBase
from assetsLoader import Loader
import json
import os


def write_save_file(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def read_save_file(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


class SaveOBJ(EnemyBase):
    def __init__(self):
        super().__init__("Save", frame_count=1, scale_percentage=(400,400))
        self.world_x = 400
        self.world_y = 300
        self.pos = [self.world_x, self.world_y]
        self.save_loader = Loader("sprites/save")
        self.save_path = self.save_loader.load("savedgame.TWOSSAVE")
        self.currchap = 1

    def draw_in_world(self, surface, cam_x, cam_y):
        frame = self.frames[self.current_frame]
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        rect = frame.get_rect(midbottom=(screen_x, screen_y))
        surface.blit(frame, rect)

    def save_game(self, world, player, triggered_once):
        data = {
            "player_x": int(player.world_x),
            "player_y": int(player.world_y),
            "current_level": int(getattr(world, "current_level", 0)),
            "triggered_once": list(triggered_once) if triggered_once is not None else [],
            "deactivated_walls": list(player.get_deact()) if hasattr(player, "get_deact") else [],
            "levels": {},
            "current_light_source": int(world.current_light_source),
        }

        try:
            level_spec_path = Loader("worlds").load("level-spec.json")
            if level_spec_path and os.path.exists(level_spec_path):
                with open(level_spec_path, "r", encoding="utf-8") as f:
                    level_spec = json.load(f)
                    for level_key, level_data in level_spec.items():
                        objs = []
                        if isinstance(level_data, dict):
                            for k, v in level_data.items():
                                if isinstance(v, list):
                                    for item in v:
                                        if isinstance(item, dict) and "x" in item and "y" in item:
                                            entry = dict(item)
                                            entry["source"] = k
                                            objs.append(entry)
                        data["levels"][level_key] = objs
        except Exception:
            pass

        try:
            current = str(getattr(world, "current_level", "current"))
            dyn = []

            for e in getattr(world, "enemies", []) or []:
                try:
                    dyn.append({
                        "type": getattr(e, "name", "enemy"),
                        "x": int(getattr(e, "world_x", 0)),
                        "y": int(getattr(e, "world_y", 0)),
                    })
                except Exception:
                    continue

            for p in getattr(world, "all_physic_objects", []) or []:
                try:
                    phys_type = getattr(p.object, "phys_type", None)
                    if not phys_type:
                        continue
                    dyn.append({
                        "type": f"physics_obj_{phys_type}",
                        "x": int(p.object.world_x),
                        "y": int(p.object.world_y),
                    })
                except Exception:
                    continue

            data["levels"][f"level_{current}_dynamic"] = dyn
        except Exception:
            pass

        write_save_file(data, self.save_path)

    def load_save(self):
        data = read_save_file(self.save_path)
        if not data:
            self._full_save = None
            return None

        self._full_save = data

        x = data.get("player_x", 0)
        y = data.get("player_y", 0)
        triggered = data.get("triggered_once", [])
        deactivated_walls = data.get("deactivated_walls", [])
        currchapter = data.get("current_level", 1)
        current_light_source = data.get("current_light_source", 2)

        return (
            int(x),
            int(y),
            list(triggered),
            list(deactivated_walls),
            int(currchapter),
            True,
            int(current_light_source),
        )
