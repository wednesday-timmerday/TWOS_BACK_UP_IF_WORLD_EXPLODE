#THIS FUCKING THING SEEMS TO BE A FUCKING https://www.youtube.com/watch?v=imH2hItIFlk



import pygame

from assetsLoader import Loader

import os

import json

import sprites.base_enemy as BaseEnemyModule

import sprites.physic_obj.physic_engine as PhysicEngineModule

from sprites.save.save import SaveOBJ

from sprites.object_state import ObjectStateManager

from collections import OrderedDict, deque

import math

import numpy as np

import ui.boxEngine.boxengine





def load_settings():

    settings_loader = Loader("ui/menu")

    settings_path = settings_loader.load("options.json")



    if settings_path and os.path.exists(settings_path):

        with open(settings_path, "r") as f:

            return json.load(f)

    else:

        print("Settings file not found, using defaults.")

        return {"fullscreen": False, "master_volume": 0.5}





# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

# Dynamic Enemy Loader

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_enemy_class_cache = {}



def get_enemy_class(enemy_type_name, *args, **kwargs):

    """

    Dynamically load and instantiate an enemy class.

    

    Tries to find a class in sprites/{enemy_name}/{enemy_name}.py

    Falls back to SaveOBJ for "save" type, or BaseEnemyModule.EnemyBase as last resort.

    

    Returns: instantiated enemy object or None if failed

    """

    enemy_type_name = enemy_type_name.lower().strip()

    

    # Special case: SaveOBJ

    if enemy_type_name == "save":

        return SaveOBJ()

    

    # Check cache first

    if enemy_type_name in _enemy_class_cache:

        enemy_class = _enemy_class_cache[enemy_type_name]

        try:

            if enemy_type_name == "lantern" or enemy_type_name == "hammer":

                return enemy_class(args[0] if args else kwargs.get("world"))

            elif enemy_type_name == "spike":

                return enemy_class(args[0] if args else kwargs.get("player"), 

                                 args[1] if len(args) > 1 else kwargs.get("world"))

            else:

                return enemy_class(*args, **kwargs)

        except Exception as e:

            print(f"[get_enemy_class] Failed to instantiate cached class '{enemy_type_name}': {e}")

            return None

    

    # Try to dynamically import the enemy class

    try:

        # Common naming patterns: ClassName, classname, ClassName in module classname.py

        sprites_path = os.path.join(os.path.dirname(__file__), "..", "sprites", enemy_type_name)

        module_path = os.path.join(sprites_path, f"{enemy_type_name}.py")

        

        if not os.path.exists(module_path):

            print(f"[get_enemy_class] Module not found: {module_path}")

            return None

        

        import importlib.util

        spec = importlib.util.spec_from_file_location(f"sprites.{enemy_type_name}", module_path)

        module = importlib.util.module_from_spec(spec)

        spec.loader.exec_module(module)

        

        # Try to find a class with a matching name (case-insensitive)

        enemy_class = None

        for attr_name in dir(module):

            attr = getattr(module, attr_name)

            if isinstance(attr, type) and attr_name.lower() == enemy_type_name:

                enemy_class = attr

                break

        

        # If exact match not found, try first uppercase letter

        if not enemy_class:

            class_name = enemy_type_name[0].upper() + enemy_type_name[1:]

            if hasattr(module, class_name):

                enemy_class = getattr(module, class_name)

        

        if not enemy_class:

            print(f"[get_enemy_class] No suitable class found in {module_path}")

            return None

        

        # Cache it

        _enemy_class_cache[enemy_type_name] = enemy_class

        

        # Instantiate with appropriate arguments

        if enemy_type_name == "lantern" or enemy_type_name == "hammer":

            return enemy_class(args[0] if args else kwargs.get("world"))

        elif enemy_type_name == "spike":

            return enemy_class(args[0] if args else kwargs.get("player"), 

                             args[1] if len(args) > 1 else kwargs.get("world"))

        else:

            return enemy_class(*args, **kwargs)

            

    except Exception as e:

        print(f"[get_enemy_class] Failed to load enemy '{enemy_type_name}': {e}")

        return None





class World_loader:

    def __init__(self, screen_size, player=None):

        cscreen = None

        self.platforms = []

        # -------------------------

        # Chunk streaming / memory limits

        # -------------------------

        self.MAX_CHUNK_CACHE = 16

        self.MAX_COLLISION_WIDTH = 8192

        self.chunk_cache = OrderedDict()  # (layer_idx, chunk_idx) -> surface

        self.collision_mask_downsample = 1

        self.prefetch_queue = deque()

        self.PREFETCH_PER_FRAME = 5

        self.PREFETCH_FRAME_INTERVAL = 1

        self._prefetch_frame_counter = 0

        self._chunks_loaded_total = 0

        self.visible_chunk_keys = set()



        # -------------------------

        # Screen / camera

        # -------------------------

        self.Screen_resolution = screen_size

        self.cam_x = 0

        self.cam_y = 0

        self.Cam_locked = False

        self._last_cam_x = 0

        self._last_cam_y = 0



        # -------------------------

        # Layers & world

        # -------------------------

        self.layers = []

        self.scaled_layers = []

        self.layer_info = []

        self.static_background = None  # optimized pre-rendered static layers



        # -------------------------

        # Entities & physics

        # -------------------------

        self.enemies = []

        self.all_physic_objects = []

        

        # -------------------------

        # Object state management

        # -------------------------

        self.object_state_manager = ObjectStateManager()



        # Player reference

        self.player = player

        # -------------------------

        # Lighting 

        # -------------------------

        self.light_sources = []

        self.current_light_source = 1

        self._light_mask_200px = self._create_light_mask(50)  # pre-rendered player light

        self._light_mask_100px = self._create_light_mask(25)  # pre-rendered extra lights

        self._cached_dark_base = None  # dark base blit (no lights)

        self._last_light_render = None



        # -------------------------

        # Settings

        # -------------------------

        self.settings = load_settings()



        # -------------------------

        # Level / spec

        # -------------------------

        self.level_spec_loader = Loader("worlds")

        self.level_spec_path = self.level_spec_loader.load("level-spec.json")

        self.current_level = 0



        if self.level_spec_path and os.path.exists(self.level_spec_path):

            with open(self.level_spec_path, "r", encoding="utf-8") as f:

                self.world_data = json.load(f)

        else:

            self.world_data = {}

        self.level_data = self.world_data.get(f"level_{self.current_level}", {})



        # -------------------------

        # Save data

        # -------------------------

        self.save_obj = SaveOBJ()

        try:

            self.save_data = self.save_obj.load_save()

        except Exception:

            self.save_data = None



        if self.save_data and isinstance(self.save_data, tuple) and len(self.save_data) >= 7:

            try:

                self.current_light_source = int(self.save_data[6])

            except Exception:

                pass



        self._light_overlay = pygame.Surface(self.Screen_resolution, pygame.SRCALPHA)

        self._light_overlay.fill((0, 0, 0, 215))



        self._big_light_mask_dark = self._light_mask_200px.copy()

        self._big_light_mask_dark.fill((0, 0, 0, 200), special_flags=pygame.BLEND_RGBA_MULT)



        self._small_light_mask_dark = self._light_mask_100px.copy()

        self._small_light_mask_dark.fill((0, 0, 0, 150), special_flags=pygame.BLEND_RGBA_MULT)



        self._light_timer = 0

        self._light_fps = 60

        self._light_dirty = True



        # -------------------------

        # Music

        # -------------------------

        music_path = f"music/{self.current_level}/BG_MC.mp3"

        if os.path.exists(music_path):

            try:

                self.Music = pygame.mixer.Sound(music_path)

                self.Music.set_volume(self.settings.get("master_volume", 0.5))

                self.Music.play(-1)

            except Exception:

                pass

        # -----------------------
        #
        # TIMER SUTFF
        # 
        # -----------------------

        self.Time_left_in_timer_that_times_the_time_in_a_timely_manner = 0.0
        self.is_timer_active = False
        self.time_to_timer = 0.0


        self.font_loader = Loader("ui/menu/")
        self.font_path = self.font_loader.load("PixelFont.ttf")
        self.timer_font = pygame.font.Font(self.font_path, 12)



        # -------------------------

        # Load world layers

        # -------------------------

        self.PARALLAX_LAYER_0 = .3

        self.load_layers()



        # collision mask / black layers are expensive on large levels

        # build them asynchronously so the menu/loading screen doesn't hang

        self._collision_thread = None

        self._collision_building = False

        self.build_collision_mask_new()



        # enemies may request the mask when they spawn; make sure they

        # either poll for availability or we attach mask once it's ready

        self.load_enemies()



        #Some shadow platform stuff

        self.shadow_platform_editor_open = False


        level_key = f"level_{getattr(self, 'current_level', self.current_level or 0)}"

        self.triggers = self.player.level_spec.get(level_key, {}).get("triggers", [])

        print(self.triggers)

        self.boxEngine = ui.boxEngine.boxengine.BoxEngine(self)

        box = (60,0,200,7)

        self.boxEngine.create_box(box)



    # -------------------------

    # Update physics

    # -------------------------

    def update_physics(self, dt):
        if self.is_timer_active and self.level_data.get("timer", None) != None:
            print("trade offer")
            self.Time_left_in_timer_that_times_the_time_in_a_timely_manner += dt

        """Update all physics engines at fixed step."""

        for engine in self.all_physic_objects:

            try:

                engine.update(dt, self.player)

            except Exception as e:

                print("Physics update error:", e)





    # -------------------------

    # Lighting helpers

    # -------------------------

    def add_light_source(self, obj, radius):

        self.light_sources.append({"obj": obj, "radius": radius})



    # -------------------------

    # Load layers

    # -------------------------

    #! TODO: make this take less time to load

    def load_layers(self):

        self.level_data = self.world_data.get(f"level_{self.current_level}", {})

        self.layer_info.clear()

        self.layers.clear()

        self.scaled_layers.clear()

        layer_paths = []



        loader = Loader(f"worlds/{self.current_level}")

        total_frames = len([n for n in os.listdir(loader.load("."))

                                if os.path.isfile(os.path.join(loader.load("."), n))])

        for i in range(total_frames):

            layer_paths.append(f"{i}.png")

        coll_layer_indices = self.level_data.get("coll_layers", [3, 4])

        coll_layer_names = {f"{i}.png" for i in coll_layer_indices}

        if self.level_data.get("timer", None) != None:
            self.is_timer_active = True
            self.time_to_timer = self.level_data.get("timer", None)
            print("kqqw")

        sans = "AAAAAAAAAA"
        print(f"Yes {sans}")


        print(f"BURNNN: {self.level_data}")

        print(f"coll_layers={self.level_data.get('coll_layers', 'NOT FOUND')}")

        for path in layer_paths:

            # collision layers (3 & 4) are heavy; we don't load/scale them here

            # because they are only needed for physics/collision.  they will be

            # processed later during mask creation.

            if path in coll_layer_names:

                img_path = loader.load(path)

                if img_path and os.path.exists(img_path):

                    self.layer_info.append({'type': 'deferred', 'path': path, 'img_path': img_path})

                    self.layers.append(None)

                    self.scaled_layers.append((path, None))

                else:

                    print(f"Collision layer not found: {path}")

                continue



            img_path = loader.load(path)

            img = None

            if img_path and os.path.exists(img_path):

                try:

                    img = pygame.image.load(img_path).convert_alpha()

                except Exception as e:

                    print(f"Failed to load full layer {img_path}: {e}")

                    img = None



            # Fallback to chunked layer

            if img is None:

                chunk_loader = Loader(f"worlds/{self.current_level}_chunks")

                base_name = path[:-4] if path.lower().endswith('.png') else path

                chunk_paths = []

                i = 0

                while True:

                    chunk_name = f"{base_name}_chunk_{i}.png"

                    chunk_path = chunk_loader.load(chunk_name)

                    if not chunk_path or not os.path.exists(chunk_path):

                        break

                    chunk_paths.append(chunk_path)

                    i += 1



                if chunk_paths:

                    # Determine base height from first chunk (cheap load)

                    try:

                        first = pygame.image.load(chunk_paths[0])

                        base_h = first.get_height()

                    except Exception as e:

                        print(f"[load_layers] failed to inspect first chunk: {e}")

                        continue



                    scale_factor = self.Screen_resolution[1] / base_h

                    chunk_widths = []

                    total_w = 0



                    # Only read sizes here (no costly convert_alpha or scaling)

                    for p in chunk_paths:

                        try:

                            tmp = pygame.image.load(p)

                            w = int(tmp.get_width() * scale_factor)

                        except Exception:

                            w = 0

                        chunk_widths.append(w)

                        total_w += w



                    info = {

                        'type': 'chunks',

                        'chunks': chunk_paths,               # file paths

                        'chunk_widths': chunk_widths,       # scaled widths (target)

                        'total_width': total_w,

                        'scale_factor': scale_factor,

                        'chunk_loader': chunk_loader,

                        'base_name': base_name,

                        'scaled_chunks': [None] * len(chunk_paths),  # will hold surfaces once created

                    }

                    self.layer_info.append(info)

                    self.layers.append(None)

                    self.scaled_layers.append((path, None))

                    continue

                else:

                    print(f"Layer not found (no full image or chunks): {path}")

                    continue



            # Full image scaling (only once)

            if img is not None and img.get_height() != self.Screen_resolution[1]:

                try:

                    scale_factor = self.Screen_resolution[1] / img.get_height()

                    new_w = int(img.get_width() * scale_factor)

                    img = pygame.transform.scale(img, (new_w, self.Screen_resolution[1]))

                except Exception:

                    pass



            self.layers.append(img)

            self.layer_info.append({'type': 'full', 'surface': img, 'path': path})

            self.scaled_layers.append((path, img))



        # Compute world size

        if self.layer_info:

            first_info = self.layer_info[0]

            if first_info['type'] == 'full':

                w = first_info['surface'].get_width()

                h = first_info['surface'].get_height()

            else:

                w = first_info['total_width']

                h = self.Screen_resolution[1]

            self.layer_length = w

            self.max_cam_x = max(0, w - self.Screen_resolution[0])

            self.max_cam_y = max(0, h - self.Screen_resolution[1])

        else:

            self.max_cam_x = self.max_cam_y = 0



        # Preload a small number of chunks near start to keep first view smooth (but don't force all)

        for idx, info in enumerate(self.layer_info):

            if info['type'] == 'chunks':

                # preload first N chunks to cover initial viewport; keep it small to avoid memory spike

                preloads = min(len(info['chunks']), 2)

                for ci in range(preloads):

                    self._get_chunk_surface(idx, ci)



        # Pre-render static layers 0-2 and collision layers 3-4

        self._render_static_background()

        self._render_collision_background()



        print(f"Loaded {len(self.layer_info)} layer metadata entries for level {self.current_level}")





    # -------------------------

    # Pre-render static layers

    # -------------------------

    def _render_static_background(self):

        total_width = self.layer_length

        height = self.Screen_resolution[1]

        coll_layer_names = {f"{i}.png" for i in self.level_data.get('coll_layers', [3, 4])}



        self.static_bg_far = pygame.Surface((total_width, height), pygame.SRCALPHA)

        self.static_bg_near = pygame.Surface((total_width, height), pygame.SRCALPHA)



        static_idx = 0

        for idx, info in enumerate(self.layer_info):

            path = info.get('path', info.get('base_name', ''))

            if path in coll_layer_names or info.get('type') == 'deferred':

                continue

            if static_idx > 2:

                break



            target = self.static_bg_far if static_idx == 0 else self.static_bg_near

            static_idx += 1



            if info['type'] == 'full':

                surf = info.get('surface')

                if surf:

                    target.blit(surf, (0, 0))

            elif info['type'] == 'chunks' and 'chunk_widths' in info:

                x = 0

                for ci, cw in enumerate(info['chunk_widths']):

                    surf = self._get_chunk_surface(idx, ci)

                    if surf:

                        target.blit(surf, (x, 0))

                    x += cw





    def _render_collision_background(self):

        total_width = self.layer_length

        height = self.Screen_resolution[1]

        coll_layer_names = {f"{i}.png" for i in self.level_data.get('coll_layers', [3, 4])}

        self.collision_background = pygame.Surface((total_width, height), pygame.SRCALPHA)



        for idx, info in enumerate(self.layer_info):

            path = info.get('path', info.get('base_name', ''))

            if path not in coll_layer_names:

                continue

            if info['type'] == 'full':

                surf = info.get('surface')

                if surf:

                    self.collision_background.blit(surf, (0, 0))

            elif info['type'] == 'chunks' and 'chunk_widths' in info:

                total = 0

                for ci, cw in enumerate(info['chunk_widths']):

                    surf = self._get_chunk_surface(idx, ci)

                    if surf:

                        self.collision_background.blit(surf, (total, 0))

                    total += cw



    # -------------------------

    # Chunk caching (optimized to create scaled chunk only once and LRU-evict)

    # -------------------------

    def _get_chunk_surface(self, layer_idx, chunk_idx):

        """

        Returns a scaled surface for the chunk (target height = screen height).

        Caches surfaces in info['scaled_chunks'] and also maintains an LRU chunk_cache that

        will evict the oldest entries and clear scaled_chunks slot to free memory.

        """

        key = (layer_idx, chunk_idx)

        # Fast LRU hit

        if key in self.chunk_cache:

            surf = self.chunk_cache.pop(key)

            self.chunk_cache[key] = surf

            return surf



        try:

            info = self.layer_info[layer_idx]

        except Exception:

            return None



        if info['type'] != 'chunks':

            return None



        # If we already created this scaled chunk, use it

        scaled_list = info.get('scaled_chunks')

        if scaled_list and scaled_list[chunk_idx] is not None:

            surf = scaled_list[chunk_idx]

            # record in LRU cache

            self.chunk_cache[key] = surf

            return surf



        # Need to create scaled chunk now (load from disk, scale to target_h)

        try:

            path = info['chunks'][chunk_idx]

            img = pygame.image.load(path).convert_alpha()

            target_h = self.Screen_resolution[1]

            sf = info.get('scale_factor', target_h / img.get_height() if img.get_height() else 1)

            target_w = int(img.get_width() * sf)

            surf = pygame.transform.scale(img, (target_w, target_h))

        except Exception as e:

            # on failure, return None and don't cache

            print(f"[get_chunk] failed to load/scale chunk {layer_idx}:{chunk_idx}: {e}")

            return None



        # store scaled chunk both in layer info and LRU cache

        try:

            info['scaled_chunks'][chunk_idx] = surf

        except Exception:

            pass



        self.chunk_cache[key] = surf



        # Enforce MAX_CHUNK_CACHE with LRU eviction; when evicting, clear scaled_chunks slot

        while len(self.chunk_cache) > self.MAX_CHUNK_CACHE:

            try:

                oldest_key, _ = next(iter(self.chunk_cache.items()))

            except StopIteration:

                break

            # Don't evict currently visible chunk keys (if tracked)

            if oldest_key in getattr(self, 'visible_chunk_keys', set()):

                break

            evicted = self.chunk_cache.popitem(last=False)

            try:

                ev_layer, ev_chunk = evicted[0]

                ev_info = self.layer_info[ev_layer]

                if ev_info.get('type') == 'chunks' and ev_info.get('scaled_chunks'):

                    # clear reference for GC and memory

                    ev_info['scaled_chunks'][ev_chunk] = None

            except Exception:

                pass



        self._chunks_loaded_total += 1

        return surf



    def _process_prefetch(self):

        self._prefetch_frame_counter = (getattr(self,'_prefetch_frame_counter',0)+1) % max(1,getattr(self,'PREFETCH_FRAME_INTERVAL',2))

        if self._prefetch_frame_counter !=0:

            return

        count = 0

        while self.prefetch_queue and count < self.PREFETCH_PER_FRAME:

            layer_idx, chunk_idx = self.prefetch_queue.popleft()

            self._get_chunk_surface(layer_idx,chunk_idx)

            count +=1



    #! TODO: Make this load system less of a if/else hell and just check the sprites/ folder



    def load_enemies(self):

        """Laadt alle enemies en physics-objecten voor de huidige level_data."""

        self.enemies.clear()

        self.all_physic_objects.clear()

        self.object_state_manager.clear()  # Clear previous state

        

        self.level_data = self.world_data.get(f"level_{self.current_level}", {})

        level_enemies = self.level_data.get("enemies", [])

        level_platform = self.level_data.get("platforms", [])



        save = self.save_obj._full_save



        if save:

            level_id = save.get("current_level", self.current_level)

            levels = save.get("levels", {})



            dyn_key = f"level_{level_id}_dynamic"

            if dyn_key in levels:

                print(f"[load_enemies] Loaded enemies from save: {dyn_key}")

                level_enemies = levels[dyn_key]



        for platform_data in level_platform:

            platformx = platform_data.get("x", 0)

            platformy = platform_data.get("y", 0)

            l = platform_data.get("width", 50)  # default width

            h = platform_data.get("height", 20) # default height



            platform_surf = pygame.Surface((l, h))

            platform_surf.fill((100, 100, 255))  # optional: give it a color



            # Store the platform as a dict with surface and position

            self.platforms.append({"surf": platform_surf, "x": platformx, "y": platformy})



        from sprites.physic_obj.physic_engine import PhysicEngine



        for enemy_data in level_enemies:

            enemy_type = enemy_data.get("type", "").lower()



            x = enemy_data.get("x", enemy_data.get("position", [0, 0])[0])

            y = enemy_data.get("y", enemy_data.get("position", [0, 0])[1])

            object_id = enemy_data.get("id", None)  # Get UUID from level spec



            # -------------------------

            # Physics objects (orb, hammer, etc.)

            # -------------------------

            if enemy_type.startswith("physics_obj_"):

                phys_name = enemy_type.replace("physics_obj_", "")



                try:

                    engine = PhysicEngine(self)



                    engine.start_physic_obj(

                        phys_name,

                        self.player,

                        self.collision_mask,

                        spawn_x=x,

                        spawn_y=y

                    )



                    # Position already set inside start_physic_obj via spawn_x/spawn_y,

                    # but sync the object attributes too just to be safe.

                    engine.body.position = (x, y)

                    engine.object.world_x = x

                    engine.object.world_y = y



                    engine.object.phys_type = phys_name

                    

                    # Register object with state manager

                    self.object_state_manager.register_object(engine.object, object_id)



                    self.all_physic_objects.append(engine)



                except Exception as e:

                    print(f"[load_enemies] Failed to spawn physics object '{phys_name}': {e}")

                    continue





            # -------------------------

            # Non-physics enemies

            # -------------------------

            else:

                try:

                    # Try dynamic loader first

                    if enemy_type == "lantern" or enemy_type == "hammer":

                        enemy = get_enemy_class(enemy_type, self)

                    elif enemy_type == "spike":

                        enemy = get_enemy_class(enemy_type, self.player, self)

                    else:

                        enemy = get_enemy_class(enemy_type)

                    

                    # Fallback to base enemy if dynamic load failed

                    if enemy is None:

                        enemy = BaseEnemyModule.EnemyBase(enemy_data.get("type", ""), frame_count=1)

                        

                except Exception as e:

                    print(f"[load_enemies] Failed to create enemy '{enemy_type}': {e}")

                    continue



                # Zet positie

                enemy.world_x = x

                enemy.world_y = y

                enemy.pos = [x, y]

                

                # Register object with state manager

                self.object_state_manager.register_object(enemy, object_id)



                # Voeg toe aan lijst

                self.enemies.append(enemy)

        

        # =====================================

        # Apply saved object states

        # =====================================

        self.save_obj.apply_object_states(self)





    # -------------------------

    # Collision mask builders (optimized to reuse scaled chunks when possible)

    # -------------------------

    def build_collision_mask(self):

        if not self.scaled_layers:

            self.collision_mask = pygame.Mask((0, 0))

            return



        world_size = self.scaled_layers[0][1].get_size()

        base_img = pygame.Surface(world_size, pygame.SRCALPHA)



        for path, img in self.scaled_layers:

            if path in ["3.png", "4.png"]:

                if img:

                    base_img.blit(img, (0,0))

        try:

            self.collision_mask = pygame.mask.from_surface(base_img, threshold=1)

        except Exception:

            self.collision_mask = pygame.Mask((0,0))



    def build_collision_mask_new(self):

        if not hasattr(self, 'layer_info') or not self.layer_info:

            self.collision_mask = pygame.Mask((0,0))

            return



        # extend support for deferred entries: load the image before building mask

        # this only happens once per level (when mask is created)

        for info in self.layer_info:

            if info.get('type') == 'deferred':

                p = info.get('img_path')

                try:

                    surf = pygame.image.load(p).convert_alpha()



                    # SCALE TO SCREEN HEIGHT

                    if surf.get_height() != self.Screen_resolution[1]:

                        scale_factor = self.Screen_resolution[1] / surf.get_height()

                        new_w = int(surf.get_width() * scale_factor)

                        surf = pygame.transform.scale(surf, (new_w, self.Screen_resolution[1]))



                    info.update({'type': 'full', 'surface': surf})

                except Exception as e:

                    print(f"[build_collision_mask_new] failed to load deferred layer {p}: {e}")

                    info['type'] = 'full'

                    info['surface'] = None



        first_info = self.layer_info[0]

        total_w = first_info['total_width'] if first_info['type'] == 'chunks' else first_info['surface'].get_width()

        target_h = self.Screen_resolution[1]



        downsample = 1

        if total_w > self.MAX_COLLISION_WIDTH:

            downsample = math.ceil(total_w / self.MAX_COLLISION_WIDTH)

            self.collision_mask_downsample = downsample

        else:

            self.collision_mask_downsample = 1



        small_w = max(1, total_w // downsample)

        small_h = max(1, target_h // downsample)

        base_img = pygame.Surface((small_w, small_h), pygame.SRCALPHA)



        for idx, info in enumerate(self.layer_info):

            base_name = info.get('path') if info['type']=='full' else info.get('base_name')

            coll_layer_names = {f"{i}.png" for i in self.level_data.get("coll_layers", [3, 4])}

            coll_layer_names |= {str(i) for i in self.level_data.get("coll_layers", [3, 4])}

            if base_name in coll_layer_names:

                if info['type']=='full':

                    surf = info.get('surface')

                    if surf:

                        try:

                            if downsample > 1:

                                small = pygame.transform.smoothscale(surf, (small_w, small_h))

                                base_img.blit(small, (0,0))

                            else:

                                base_img.blit(surf, (0,0))

                        except Exception as e:

                            print(f"[build_collision_mask_new] failed scaling full surface: {e}")

                else:

                    x = 0

                    for ci, chunk_path in enumerate(info['chunks']):

                        # Prefer already-created scaled chunk (full-height). If available and no downsample,

                        # use it; otherwise load & scale directly to the small size to save memory.

                        try:

                            scaled_chunk = None

                            if downsample <= 1:

                                # we want full resolution chunk for collision mask

                                scaled_chunk = info.get('scaled_chunks', [None])[ci]

                                if scaled_chunk is None:

                                    # create it (full target height)

                                    scaled_chunk = self._get_chunk_surface(idx, ci)

                            if downsample > 1:

                                # create a small version directly from disk to avoid creating huge surface

                                ch = pygame.image.load(chunk_path).convert_alpha()

                                scaled_w = max(1, int(info['chunk_widths'][ci] // downsample))

                                small_chunk = pygame.transform.smoothscale(ch, (scaled_w, small_h))

                                base_img.blit(small_chunk, (x//downsample, 0))

                            else:

                                if scaled_chunk:

                                    small = pygame.transform.smoothscale(scaled_chunk, (info['chunk_widths'][ci], small_h)) if downsample > 1 else scaled_chunk

                                    base_img.blit(scaled_chunk, (x//downsample, 0))

                        except Exception as e:

                            print(f"[build_collision_mask_new] chunk {idx}:{ci} failed: {e}")

                        x += info['chunk_widths'][ci]



        try:

            self.collision_mask = pygame.mask.from_surface(base_img, threshold=1)

        except Exception:

            self.collision_mask = pygame.Mask((0,0))



        self._render_collision_background()



    # -------------------------

    # Create pre-rendered light mask

    # -------------------------

    def _create_light_mask(self, radius):

        size = radius * 2

        mask = pygame.Surface((size, size), pygame.SRCALPHA)

        

        y, x = np.ogrid[:size, :size]

        dist = np.sqrt((x - radius)**2 + (y - radius)**2)

        

        alpha = np.clip(1.0 - (dist / radius) ** 1.5, 0, 1)

        alpha = (alpha * 255).astype(np.uint8)

        

        # Schrijf direct naar surface array

        arr = pygame.surfarray.pixels_alpha(mask)

        arr[:] = alpha.T  

        del arr  # unlock surface

        

        rgb = pygame.surfarray.pixels3d(mask)

        rgb[:] = 255

        del rgb

        

        return mask.convert_alpha()



    # -------------------------

    # Camera

    # -------------------------

    def update_camera(self, player_x, player_y):

        half_width = self.Screen_resolution[0] / 2.0

        self.cam_x = max(0.0, min(float(self.max_cam_x), float(player_x) - half_width))

        self.Cam_locked = self.cam_x <= 0 or self.cam_x >= self.max_cam_x

        self.cam_y = 0.0



    # -------------------------

    # Draw black layer with lights

    # -------------------------

    def draw_black_layer(self, screen, player_or_x, player_y=None):

        # Skip entirely if lighting disabled

        if not self.light_sources and self.current_light_source == 1:

            return



        # --------- LIGHT FPS CAP (â‰ˆ60 FPS) ---------

        self._light_frame_counter = getattr(self, "_light_frame_counter", 0) + 1

        if self._light_frame_counter < 1 and not getattr(self, "_light_dirty", True):

            screen.blit(self._light_overlay, (0, 0))

            return

        self._light_frame_counter = 0

        self._light_dirty = False



        self._light_overlay.fill((0, 0, 0, 180))  



        if hasattr(player_or_x, "hit_box"):

            cx = int(player_or_x.hit_box.centerx - self.cam_x)

            cy = int(player_or_x.hit_box.centery - self.cam_y)

        else:

            cx = int(player_or_x - self.cam_x)

            cy = int((player_y or 0) - self.cam_y)



        screen_w, screen_h = self.Screen_resolution



        # Cull player light if off-screen

        if -220 < cx < screen_w + 220 and -220 < cy < screen_h + 220:

            rect = self._big_light_mask_dark.get_rect(center=(cx, cy))

            self._light_overlay.blit(

                self._big_light_mask_dark,

                rect,

                special_flags=pygame.BLEND_RGBA_SUB

            )



        # --------- OTHER LIGHT SOURCES ---------

        for light in self.light_sources:

            obj = light.get("obj")

            if not obj:

                continue



            lx = int(obj.world_x - self.cam_x)

            ly = int(obj.world_y - self.cam_y)



            # HARD CULL (VERY IMPORTANT)

            if lx < -150 or lx > screen_w + 150:

                continue

            if ly < -150 or ly > screen_h + 150:

                continue



            rect = self._small_light_mask_dark.get_rect(center=(lx, ly))

            self._light_overlay.blit(

                self._small_light_mask_dark,

                rect,

                special_flags=pygame.BLEND_RGBA_SUB

            )



        # --------- FINAL BLIT ---------

        screen.blit(self._light_overlay, (0, 0))







    # -------------------------

    # Draw world

    # -------------------------

    def draw_world(self, screen, player_x, player_y):

        self.screen = screen

        self.update_camera(player_x, player_y)


        cam_x = self.cam_x  # float

        cam_y = self.cam_y





        # Check if camera moved significantly

        cam_moved = abs(cam_x - self._last_cam_x) > 8 or abs(cam_y - self._last_cam_y) > 8

        

        # ALWAYS draw static background (single blit)

        if self.static_bg_far:

            visible_x = cam_x * self.PARALLAX_LAYER_0

            clip_rect = pygame.Rect(int(visible_x), 0, self.Screen_resolution[0], self.Screen_resolution[1])

            screen.blit(self.static_bg_far, (0, 0), area=clip_rect)



        if self.static_bg_near:

            screen.blit(self.static_bg_near, (-cam_x, 0))   # float offset â€” pygame truncates at blit



        if hasattr(self, 'collision_background') and self.collision_background:

            screen.blit(self.collision_background, (-cam_x, 0))

        

        # Only process prefetch when camera moves

        if cam_moved:

            self._process_prefetch()

            self._last_cam_x = cam_x

            self._last_cam_y = cam_y



        # Pre-cache viewport culling bounds (calculated once, not per entity)

        screen_w = self.Screen_resolution[0]

        screen_h = self.Screen_resolution[1]

        margin = 200

        cam_x_min = cam_x - margin

        cam_x_max = cam_x + screen_w + margin

        cam_y_min = cam_y - margin

        cam_y_max = cam_y + screen_h + margin

        

        # Draw enemies (minimal overhead - direct attribute access)

        for enemy in self.enemies:

            ex = getattr(enemy, 'world_x', 0)

            ey = getattr(enemy, 'world_y', 0)

            if cam_x_min < ex < cam_x_max and cam_y_min < ey < cam_y_max:

                if hasattr(enemy, 'draw_in_world'):

                    enemy.draw_in_world(screen, cam_x, cam_y)



        # Draw physics objects

        for obj in self.all_physic_objects:

            ox = getattr(obj, 'world_x', 0)

            oy = getattr(obj, 'world_y', 0)

            if cam_x_min < ox < cam_x_max and cam_y_min < oy < cam_y_max:

                if hasattr(obj, 'draw_in_world'):

                    obj.draw_in_world(screen, cam_x, cam_y)



        for platform in self.platforms:

            screen.blit(platform["surf"], (platform["x"] - cam_x, platform["y"] - cam_y))


    def draw_shadow(self, screen):

        if self.shadow_platform_editor_open:

            with_btns = True

            self.boxEngine.draw(screen, with_btns)



    def draw_timer(self, screen):
        shit_to_render = self.timer_font.render(f"Timer: {round(self.time_to_timer - self.Time_left_in_timer_that_times_the_time_in_a_timely_manner)}", True, (255,255,255)) 
        if round(self.time_to_timer - self.Time_left_in_timer_that_times_the_time_in_a_timely_manner) <= 0 and self.is_timer_active and self.level_data.get("timer", None) != None:
            self.player.die(self)
            print(f"1: {self.time_to_timer}, 2: {self.Time_left_in_timer_that_times_the_time_in_a_timely_manner}")
        if self.level_data.get("timer", None) != None and not self.player.dead:
            screen.blit(shit_to_render, (10,10))
    # -------------------------

    # Collision query

    # -------------------------

    def check_collision(self, rect: pygame.Rect) -> bool:

        if not hasattr(self, "collision_mask"):

            return False

        sf = getattr(self,'collision_mask_downsample',1)

        if sf <= 1:

            offset = (int(rect.x), int(rect.y))

            test_mask = pygame.Mask((int(rect.width), int(rect.height)), fill=True)

            return self.collision_mask.overlap(test_mask, offset) is not None

        else:

            sx = int(math.floor(rect.x/sf))

            sy = int(math.floor(rect.y/sf))

            sw = max(1, int(math.ceil(rect.width/sf)))

            sh = max(1, int(math.ceil(rect.height/sf)))

            mask_w, mask_h = self.collision_mask.get_size()

            if sx + sw <=0 or sy + sh <=0 or sx>=mask_w or sy>=mask_h:

                return False

            if sx<0:

                sw+=sx

                sx=0

            if sy<0:

                sh+=sy

                sy=0

            if sx+sw>mask_w:

                sw = mask_w-sx

            if sy+sh>mask_h:

                sh = mask_h-sy

            if sw<=0 or sh<=0:

                return False

            test_mask = pygame.Mask((sw,sh), fill=True)

            return self.collision_mask.overlap(test_mask,(sx,sy)) is not None



    def draw_physic_objects(self, screen, dt=None):

        for engine in self.all_physic_objects:

            # Draw only â€” update is handled by update_physics() called from main

            try:

                if hasattr(engine, "draw"):

                    engine.draw(screen, self.cam_x, self.cam_y)

            except Exception as e:

                print("Physic draw error:", e)



    def change_level(self, level_id, player):

        # Save current level state before switching

        try:

            self.save_obj.save_game(self, player, False)

        except Exception as e:

            print(f"Warning: Failed to save state when switching levels: {e}")

        

        self.current_level = level_id

        self.light_sources = []  # Clear light sources from previous level

        self.load_layers()

        self.build_collision_mask_new()

        self.Time_left_in_timer_that_times_the_time_in_a_timely_manner = 0.0
        self.is_timer_active = False

        for phys_obj in self.all_physic_objects:

            try:

                # physics objects might not yet have a mask; the thread will fix

                if hasattr(self, 'collision_mask'):

                    phys_obj.add_collision_mask(self.collision_mask)

            except Exception:

                pass



        self.load_enemies()



        level_key = f"level_{getattr(self, 'current_level', self.current_level or 0)}"

        self.triggers = self.player.level_spec.get(level_key, {}).get("triggers", [])

        print(self.triggers)

        self.boxEngine.refresh()



    def toggle_shadow_platform_editor(self):

        if self.toggle_shadow_platform_editor == True:

            self.shadow_platform_editor_open = False

        else:

            self.shadow_platform_editor_open = True
