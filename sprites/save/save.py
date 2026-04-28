from sprites.base_enemy import EnemyBase
from sprites.object_state import StateSerializable
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


class SaveOBJ(StateSerializable, EnemyBase):
    def __init__(self):
        StateSerializable.__init__(self)
        EnemyBase.__init__(self, "Save", frame_count=1, scale_percentage=(400,400))
        self.object_type = "save"
        self.world_x = 400
        self.world_y = 300
        self.pos = [self.world_x, self.world_y]
        self.save_loader = Loader("sprites/save")
        self.save_path = self.save_loader.load("savedgame.TWOSSAVE")
        self.currchap = 1
    
    def serialize_state(self):
        """Save save point state"""
        return {
            "x": int(self.world_x),
            "y": int(self.world_y),
        }
    
    def deserialize_state(self, state):
        """Restore save point state"""
        self.world_x = state.get("x", 400)
        self.world_y = state.get("y", 300)
        self.pos = [self.world_x, self.world_y]

    def draw_in_world(self, surface, cam_x, cam_y):
        frame = self.frames[self.current_frame]
        screen_x = self.world_x - cam_x
        screen_y = self.world_y - cam_y
        rect = frame.get_rect(midbottom=(screen_x, screen_y))
        surface.blit(frame, rect)

    def save_game(self, world, player, triggered_once):
        # Load existing save to preserve other levels' object states
        existing_save = read_save_file(self.save_path)
        if existing_save:
            data = existing_save
        else:
            data = {
                "player_x": 0,
                "player_y": 0,
                "current_level": 0,
                "triggered_once": [],
                "deactivated_walls": [],
                "levels": {},
                "current_light_source": 1,
                "object_states": {},
            }
        
        # Update current game state
        data["player_x"] = int(player.world_x)
        data["player_y"] = int(player.world_y)
        data["current_level"] = int(getattr(world, "current_level", 0))
        data["triggered_once"] = list(triggered_once) if triggered_once is not None else []
        data["deactivated_walls"] = list(player.get_deact()) if hasattr(player, "get_deact") else []
        data["current_light_source"] = int(world.current_light_source)

        # =====================================
        # Save object states organized by level
        # =====================================
        try:
            state_manager = getattr(world, "object_state_manager", None)
            if state_manager:
                current_level = int(getattr(world, "current_level", 0))
                level_key = f"level_{current_level}"
                
                # Initialize object_states if needed
                if "object_states" not in data:
                    data["object_states"] = {}
                
                # Save current level's object states
                level_states = state_manager.save_all_states()
                data["object_states"][level_key] = level_states
                print(f"[SaveOBJ.save_game] ✓ Saved state for {len(level_states)} objects in {level_key}")
                for obj_id, state_data in level_states.items():
                    obj_type = state_data.get("type", "unknown")
                    print(f"  - {obj_type} (ID: {obj_id}): {state_data.get('state', {})}")
        except Exception as e:
            print(f"[SaveOBJ.save_game] ✗ Failed to save object states: {e}")

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
                        "id": getattr(e, "object_id", None),
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
                        "id": getattr(p.object, "object_id", None),
                    })
                except Exception:
                    continue

            data["levels"][f"level_{current}_dynamic"] = dyn
        except Exception:
            pass

        write_save_file(data, self.save_path)
        
        # Reload save data so _full_save is up-to-date
        self.load_save()

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

    def apply_object_states(self, world):
        """
        Apply saved object states to the world for the current level.
        Call this after enemies have been loaded.
        
        Args:
            world: The World_loader instance
        """
        if not hasattr(self, "_full_save") or not self._full_save:
            print(f"[SaveOBJ.apply_object_states] ✗ No save data loaded")
            return
        
        # Get object states for the current level
        object_states = self._full_save.get("object_states", {})
        if not object_states:
            print(f"[SaveOBJ.apply_object_states] ✗ No object_states in save file")
            return
        
        current_level = int(getattr(world, "current_level", 0))
        level_key = f"level_{current_level}"
        
        # Get states for this specific level
        level_object_states = object_states.get(level_key, {})
        if not level_object_states:
            print(f"[SaveOBJ.apply_object_states] ✗ No states for {level_key}")
            return
        
        state_manager = getattr(world, "object_state_manager", None)
        if not state_manager:
            print(f"[SaveOBJ.apply_object_states] ✗ No state_manager in world")
            return
        
        try:
            print(f"[SaveOBJ.apply_object_states] → Applying {len(level_object_states)} saved states to {level_key}")
            state_manager.load_all_states(level_object_states)
        except Exception as e:
            print(f"[SaveOBJ.apply_object_states] ✗ Failed to apply object states: {e}")
