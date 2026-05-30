import pygame

import os

import json

import time

import threading

import traceback

import tkinter as tk

from tkinter import ttk, scrolledtext, filedialog, messagebox

import gc



from pathlib import Path

from pypresence import Presence



from assetsLoader import Loader


gc.collect()



# -----------------------

# Multiplayer (optional)

# -----------------------

try:

    from multiplayer.multiplayer import MP as _MP

    MULTIPLAYER_AVAILABLE = True

except Exception:

    _MP = None

    MULTIPLAYER_AVAILABLE = False



# --join flag: full multiplayer (render + listen).

# Without it: still connects + sends, but never draws/receives others.

import sys

MP_JOIN_MODE = "--join" in sys.argv



# -----------------------

# Config / Globals

# -----------------------

client_id = "1441698591579312168"

rpc = Presence(client_id)

rpc_connected = False



SCREEN_RESOLUTION = (1280, 720)   # actual window size

MINI_RESOLUTION   = (320, 180)    # low-res renderer

FPS               = 60           # set to 0 for uncapped

OPTIONS_FILE      = r"C:\TWOSFILES\options.json"



BASE_DIR  = Path(__file__).parent

CACHE_DIR = BASE_DIR / "cache"



LOADING_SCALE = 10

loading_font  = None



DEBUG_FORCE_RED_SQUARE = False



# -----------------------

# Background RPC connect

# -----------------------

def rpc_background_connect():

    global rpc_connected

    try:

        rpc.connect()

        rpc_connected = True

    except Exception:

        pass



threading.Thread(target=rpc_background_connect, daemon=True).start()



# -----------------------

# Cache helpers

# -----------------------

def save_json_cache(filename, data):

    CACHE_DIR.mkdir(exist_ok=True)

    with open(CACHE_DIR / filename, "w", encoding="utf-8") as f:

        json.dump(data, f)



def load_json_cache(filename):

    path = CACHE_DIR / filename

    if path.exists():

        with open(path, "r", encoding="utf-8") as f:

            return json.load(f)

    return None



def save_surface_cache(filename, surface):

    CACHE_DIR.mkdir(exist_ok=True)

    pygame.image.save(surface, str(CACHE_DIR / filename))



def load_surface_cache(filename):

    path = CACHE_DIR / filename

    if path.exists():

        return pygame.image.load(str(path)).convert_alpha()

    return None



# -----------------------

# Options

# -----------------------

options_path = OPTIONS_FILE


def load_options():

    if options_path and os.path.exists(options_path):

        try:

            with open(options_path, "r", encoding="utf-8") as f:

                return json.load(f)

        except Exception:

            pass

    return {"fullscreen": False, "master_volume": 0.5}


def save_options(options):

    os.makedirs(os.path.dirname(options_path), exist_ok=True)

    with open(options_path, "w", encoding="utf-8") as f:

        json.dump(options, f, indent=4)



# -----------------------

# Init pygame

# -----------------------

def init_pygame(options):

    os.environ["SDL_RENDER_VSYNC"]       = "0"

    os.environ["SDL_VIDEO_X11_FORCE_EGL"] = "0"

    pygame.init()

    try:

        pygame.mixer.init()

    except Exception:

        pass

    pygame.font.init()



    fps_font = pygame.font.SysFont("Arial", 18)



    flags = pygame.SCALED | pygame.DOUBLEBUF | pygame.HWSURFACE | pygame.RESIZABLE

    if options.get("fullscreen"):

        flags |= pygame.FULLSCREEN



    screen = pygame.display.set_mode(SCREEN_RESOLUTION, flags, vsync=1)

    pygame.display.set_caption("The Weight of Shadows")



    renderer = pygame.Surface(MINI_RESOLUTION)



    try:

        icon_loader = Loader("icon")

        icon_path   = icon_loader.load("lantern.png")

        if icon_path and os.path.exists(icon_path):

            icon_surface = pygame.image.load(icon_path).convert_alpha()

            pygame.display.set_icon(icon_surface)

    except Exception:

        pass



    pygame.mixer.music.set_volume(options.get("master_volume", 0.5))

    return screen, fps_font, renderer



# -----------------------

# Loading screen

# -----------------------

def draw_loading_screen_old(surface, progress, text="Loading..."):

    surface.fill((30, 30, 30))

    font  = pygame.font.SysFont("Arial", 32, bold=True)

    label = font.render(text, True, (255, 200, 50))

    surface.blit(label, (surface.get_width() // 2 - label.get_width() // 2, 140))

    bar_w, bar_h = 500, 40

    x = surface.get_width() // 2 - bar_w // 2

    y = 220

    pygame.draw.rect(surface, (100, 100, 100), (x, y, bar_w, bar_h), border_radius=10)

    fill_w = max(0, int(bar_w * max(0.0, min(1.0, progress))))

    if fill_w > 4:

        pygame.draw.rect(surface, (255, 200, 50), (x + 2, y + 2, fill_w - 4, bar_h - 4), border_radius=10)

    dot_font  = pygame.font.SysFont("Arial", 28)

    dot_label = dot_font.render("." * (int(time.time() * 2) % 4), True, (255, 200, 50))

    surface.blit(dot_label, (surface.get_width() // 2 + label.get_width() // 2 + 10, 140))



def draw_loading_screen(surface, progress, text="LOADING...", inside_img=None, outline_img=None):

    global loading_font

    progress = max(0.0, min(1.0, progress))

    surface.fill((20, 35, 41))



    if loading_font is None:

        try:

            fl = Loader("ui/menu")

            fp = fl.load("loadmenufont.ttf")

            if fp and os.path.exists(fp):

                loading_font = pygame.font.Font(fp, 32)

            else:

                loading_font = pygame.font.SysFont("Arial", 32, bold=True)

        except Exception:

            loading_font = pygame.font.SysFont("Arial", 32, bold=True)



    label = loading_font.render(text, True, (230, 230, 230))

    surface.blit(label, label.get_rect(center=(surface.get_width() // 2, 80)))



    if not inside_img or not outline_img:

        draw_loading_screen_old(surface, progress, text)

        return



    bar_w, bar_h = inside_img.get_size()

    bar_x   = surface.get_width()  // 2 - bar_w // 2

    bar_y   = surface.get_height() // 2 - bar_h // 2

    fill_w  = int(bar_w * progress)

    surface.blit(outline_img, (bar_x, bar_y))

    if fill_w > 0:

        source_rect = pygame.Rect(0, 0, fill_w, bar_h)

        surface.blit(inside_img, (bar_x + 4 * LOADING_SCALE, bar_y + 8 * LOADING_SCALE), source_rect)



# -----------------------

# Error GIF / window

# -----------------------

def play_error_gif(error_text):

    import pygame as _pg

    from PIL import Image, ImageSequence



    _pg.quit()

    _pg.init()

    try:

        _pg.mixer.init()

    except Exception:

        pass

    _pg.font.init()



    screen = _pg.display.set_mode((1080, 720))

    _pg.display.set_caption("Dog is sleepy")



    loader     = Loader("ui/error")

    gif_path   = loader.load("eepy.gif")

    music_path = loader.load("thatstoobad.mp3")



    try:

        if music_path and os.path.exists(music_path):

            _pg.mixer.music.load(music_path)

            _pg.mixer.music.play(-1)

    except Exception:

        pass



    gif    = Image.open(gif_path)

    frames = []

    durations = []

    for frame in ImageSequence.Iterator(gif):

        frame = frame.convert("RGBA")

        data  = frame.tobytes()

        py_frame = _pg.image.fromstring(data, frame.size, frame.mode)

        frames.append(py_frame)

        durations.append(frame.info.get("duration", 100))



    clock       = _pg.time.Clock()

    frame_index = 0

    running     = True

    timer       = 0



    while running:

        dt = clock.tick(60)

        timer += dt

        for event in _pg.event.get():

            if event.type in (_pg.QUIT, _pg.KEYDOWN):

                running = False



        if timer >= durations[frame_index]:

            timer = 0

            frame_index = (frame_index + 1) % len(frames)



        screen.fill((0, 0, 0))

        screen.blit(frames[frame_index], frames[frame_index].get_rect())

        _pg.display.flip()



    try:

        _pg.mixer.music.stop()

    except Exception:

        pass

    _pg.quit()



ERROR_ICON = "âŒ"

def show_error_window(error_text):

    root = tk.Tk()

    root.title("MAN, I REALLY FUCKED UP")

    root.geometry("750x950")

    root.configure(bg="#1e1e1e")

    root.resizable(True, True)

    style = ttk.Style()

    try:

        style.theme_use("clam")

    except Exception:

        pass

    style.configure("TFrame",        background="#1e1e1e")

    style.configure("TLabel",        background="#1e1e1e", foreground="#ffffff", font=("Segoe UI", 11))

    style.configure("Header.TLabel", font=("Segoe UI", 15, "bold"))

    style.configure("TButton",       background="#3c3c3c", foreground="#ffffff", font=("Segoe UI", 10), padding=6)

    style.map("TButton", background=[("active", "#505050")])



    frame  = ttk.Frame(root)

    frame.pack(fill="both", expand=True, padx=15, pady=15)

    header = ttk.Label(frame, text=f"{ERROR_ICON} I AM BAD AT CODING", style="Header.TLabel")

    header.pack(anchor="w", pady=(0, 10))



    text_box = scrolledtext.ScrolledText(

        frame, wrap=tk.WORD, font=("Consolas", 11),

        background="#252526", foreground="#d4d4d4", insertbackground="white"

    )

    text_box.insert(tk.END, error_text)

    text_box.config(state=tk.DISABLED)

    text_box.pack(fill="both", expand=True)



    button_frame = ttk.Frame(frame)

    button_frame.pack(fill="x", pady=10)



    def copy_to_clipboard():

        root.clipboard_clear()

        root.clipboard_append(error_text)

        messagebox.showinfo("Copied", "The full traceback has been copied!")



    def save_error():

        filename = filedialog.asksaveasfilename(

            initialfile="error_log.txt", defaultextension=".txt",

            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]

        )

        if filename:

            with open(filename, "w", encoding="utf-8") as f:

                f.write(error_text)

            messagebox.showinfo("Saved", f"Error log saved to:\n{filename}")



    ttk.Button(button_frame, text="Copy", command=copy_to_clipboard).pack(side="left", padx=5)

    ttk.Button(button_frame, text="Save", command=save_error).pack(side="left", padx=5)

    root.mainloop()



# -----------------------

# Small helpers

# -----------------------

class TobyRadiationFoxLocal:

    def __init__(self):

        self.surface = pygame.Surface((64, 64), pygame.SRCALPHA)

    def get_surface(self):

        return self.surface

    def set_surface(self, surface):

        self.surface = surface



def safe_load_image(path):

    try:

        if path and os.path.exists(path):

            return pygame.image.load(path).convert_alpha()

    except Exception:

        pass

    return None



def blit_renderer_to_screen(screen, renderer):

    pygame.transform.scale(renderer, SCREEN_RESOLUTION, screen)



def get_cam_target(player):

    cx = player.world_x + player.hitbox_offset_x + player.hit_box.width  / 2.0

    cy = player.world_y + player.hitbox_offset_y + player.hit_box.height / 2.0

    return cx, cy



# -----------------------
# Debug Level Warp Popup
# -----------------------

def get_available_levels():
    """Dynamically get available levels from worlds directory."""
    import os
    worlds_dir = "worlds"
    if not os.path.exists(worlds_dir):
        return []
    
    levels = []
    for item in os.listdir(worlds_dir):
        item_path = os.path.join(worlds_dir, item)
        if os.path.isdir(item_path) and item.isdigit():
            levels.append(item)
    
    return sorted(levels, key=lambda x: int(x))


class DebugLevelWarp:
    def __init__(self, screen):
        self.screen = screen
        self.active = False
        self.selected_index = 0
        self.levels = []
        self.font = pygame.font.SysFont("Arial", 20, bold=True)
        self.small_font = pygame.font.SysFont("Arial", 16)

    def set_levels(self, level_list):
        """Set available levels."""
        self.levels = level_list if level_list else ["test_level"]

    def open(self):
        self.active = True
        self.selected_index = 0

    def close(self):
        self.active = False

    def handle_input(self):
        """Handle keyboard input for level selection."""
        keys = pygame.key.get_pressed()
        if keys[pygame.K_UP]:
            self.selected_index = (self.selected_index - 1) % len(self.levels)
            pygame.time.delay(100)
        elif keys[pygame.K_DOWN]:
            self.selected_index = (self.selected_index + 1) % len(self.levels)
            pygame.time.delay(100)
        elif keys[pygame.K_RETURN]:
            return self.levels[self.selected_index]
        elif keys[pygame.K_ESCAPE]:
            self.close()
        return None

    def draw(self):
        """Draw the level warp popup on screen."""
        if not self.active or not self.levels:
            return

        overlay = pygame.Surface(self.screen.get_size())
        overlay.set_alpha(200)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))

        popup_width, popup_height = 500, 400
        popup_x = self.screen.get_width() // 2 - popup_width // 2
        popup_y = self.screen.get_height() // 2 - popup_height // 2

        pygame.draw.rect(self.screen, (50, 50, 50), (popup_x, popup_y, popup_width, popup_height))
        pygame.draw.rect(self.screen, (200, 200, 200), (popup_x, popup_y, popup_width, popup_height), 3)

        title = self.font.render("DEBUG: SELECT LEVEL", True, (255, 200, 50))
        self.screen.blit(title, (popup_x + popup_width // 2 - title.get_width() // 2, popup_y + 20))

        y_offset = popup_y + 70
        for i, level in enumerate(self.levels):
            if i == self.selected_index:
                color = (255, 255, 0)
                pygame.draw.rect(self.screen, (100, 100, 0), (popup_x + 10, y_offset - 5, popup_width - 20, 25))
                text = self.font.render(f"> {level}", True, color)
            else:
                color = (200, 200, 200)
                text = self.small_font.render(f"  {level}", True, color)

            self.screen.blit(text, (popup_x + 20, y_offset))
            y_offset += 30

        instructions = [
            "UP/DOWN: Navigate",
            "ENTER: Warp to level",
            "ESC: Cancel"
        ]
        inst_y = popup_y + popup_height - 80
        for inst in instructions:
            inst_text = self.small_font.render(inst, True, (150, 150, 150))
            self.screen.blit(inst_text, (popup_x + 20, inst_y))
            inst_y += 20





# -----------------------

# MAIN

# -----------------------

def main():

    global loading_font, rpc_connected



    options = load_options()

    screen, fps_font, renderer = init_pygame(options)



    # â”€â”€ Loading bar assets â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    loader = Loader("ui/menu/images_for_load_img_i_guess_idk")

    loading_path = bar_path = None

    try:

        loading_path = loader.load("loadthingy.png")

    except Exception:

        pass

    try:

        bar_path = loader.load("outlining.png")

    except Exception:

        pass



    loading_image = safe_load_image(loading_path)

    bar_image     = safe_load_image(bar_path)



    if loading_image:

        try:

            loading_image = pygame.transform.scale(

                loading_image,

                (int(loading_image.get_width()  * LOADING_SCALE),

                 int(loading_image.get_height() * LOADING_SCALE))

            )

        except Exception:

            pass

    if bar_image:

        try:

            bar_image = pygame.transform.scale(

                bar_image,

                (int(bar_image.get_width()  * LOADING_SCALE),

                 int(bar_image.get_height() * LOADING_SCALE))

            )

        except Exception:

            pass



    try:

        draw_loading_screen(screen, 0.0, "LOADING...", loading_image, bar_image)

        pygame.display.flip()

    except Exception:

        pass



    try:

        from ui.tobytank.toby import TobyRadiationFox as ImportedToby

    except Exception:

        ImportedToby = None



    pygame.time.delay(120)

    if ImportedToby:

        try:

            toby = ImportedToby()

            try:

                toby.draw(screen)

            except Exception:

                pass

            pygame.display.flip()

        except Exception:

            pass



    pygame.time.delay(120)

    try:

        draw_loading_screen(screen, 0.15, "LOADING...", loading_image, bar_image)

        pygame.display.flip()

    except Exception:

        pass



    clock = pygame.time.Clock()

    dt    = clock.tick(FPS) / 1000.0

    dt    = min(dt, 0.125)



    try:

        from ui.menu.menu import Menu, save_options

        from ui.menu import saymyname

    except Exception:

        Menu         = None

        save_options = lambda x: None

        saymyname    = None



    menu_obj = Menu(options) if Menu else None

    name_obj = saymyname.NameScreen(screen) if saymyname else None



    if rpc_connected:

        try:

            rpc.update(state="In Menu")

        except Exception:

            pass



    try:

        draw_loading_screen(screen, 0.35, "LOADING...", loading_image, bar_image)

        pygame.display.flip()

    except Exception:

        pass



    try:

        import sprites.Player.Player as PlayerModule
        import ui.fight.fight as FightModule

    except Exception as e:

        print(f"Error importing Player module: {e}")

        PlayerModule = None
    

    try:

        player = PlayerModule.Player(screen=screen) # if PlayerModule else None
        fight_loader = FightModule.Fight(renderer, screen)

    except Exception as e:

        print(f"Error initializing player: {e}")



    try:

        draw_loading_screen(screen, 0.55, "LOADING...", loading_image, bar_image)

        pygame.display.flip()

    except Exception:

        pass



    try:

        draw_loading_screen(screen, 0.75, "LOADING...", loading_image, bar_image)

        pygame.display.flip()

    except Exception:

        pass



    try:

        from worlds.world_loader import World_loader as WorldModule

    except Exception as e:

        print(e)

        WorldModule = None



    world_data   = load_json_cache("world.json")

    try:

        world_loader = WorldModule(MINI_RESOLUTION, player)

    except Exception as e:

        print(e)

    if not world_data:

        save_json_cache("world.json", {"dummy": True})



    try:

        draw_loading_screen(screen, 1.0, "READY", loading_image, bar_image)

        pygame.display.flip()

    except Exception:

        pass



    pygame.time.delay(300)



    # â”€â”€ Menu â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    menu_result = None

    if menu_obj:

        try:

            menu_result = menu_obj.draw(screen)

        except Exception:

            traceback.print_exc()

            menu_result = None



    if menu_result == "reset" and PlayerModule:

        player = PlayerModule.Player(screen)



    options = menu_obj.settings if menu_obj else options

    try:

        save_options(options)

    except Exception:

        pass



    # â”€â”€ Name screen â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    if name_obj:

        try:

            name_obj.draw(dt)

            if getattr(name_obj, "chara_name", "") == "LEBREAH" and player:

                player.lebreah = True

                player.refresh_animation()

            player.name       = name_obj.chara_name
            player.true_name  = os.getlogin()
            player.maker_name = name_obj.creator_name

        except Exception:

            pass



    # â”€â”€ Multiplayer init â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    # mp = None

    # if MULTIPLAYER_AVAILABLE and _MP is not None:

    #     try:

    #         mp = _MP(

    #             player,

    #             room_id="main_world",

    #             name=getattr(player, "name", "???") or "???",

    #             join_mode=MP_JOIN_MODE,

    #         )

    #         mp.start()

    #         print(f"[MP] Multiplayer started! join_mode={MP_JOIN_MODE}")

    #     except Exception:

    #         traceback.print_exc()

    #         mp = None



    if player is None or world_loader is None:

        error_msg = "Critical modules failed to load (player or world). Check imports."

        print(error_msg)

        show_error_window(error_msg)

        return



    # â”€â”€ Main loop â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    running             = True

    last_fps_value      = -1

    last_fps_text       = None

    physics_accumulator = 0.0

    physics_step        = 1.0 / 60.0

    debug_warp_popup    = DebugLevelWarp(screen)



    while running:

        dt = clock.tick(FPS) / 1000.0

        dt = min(dt, 1 / 30)

        if dt > 0.2:

            dt = 0



        for event in pygame.event.get():

            if event.type == pygame.QUIT:

                running = False

            elif event.type == pygame.KEYDOWN:

                if event.key == pygame.K_q and options.get('debug', 0.0) > 0.0 and not debug_warp_popup.active:

                    debug_warp_popup.set_levels(get_available_levels())

                    debug_warp_popup.open()



        # Debug level warp popup input

        if debug_warp_popup.active:

            selected_level = debug_warp_popup.handle_input()

            if selected_level:

                try:

                    world_loader.change_level(selected_level, player)

                    print(f"[DEBUG] Warped to level: {selected_level}")

                except Exception as e:

                    print(f"Error warping to level: {e}")

                debug_warp_popup.close()


        # Clear renderer

        renderer.fill((0, 0, 0))



        # Multiplayer tick

        # if mp:

        #     try:

        #         mp.tick(dt)

        #     except Exception:

        #         pass



        # Update player

        try:

            player.update(world_loader, renderer, dt, 1.0, player, fight_loader=fight_loader)

        except Exception:

            traceback.print_exc()



        # Fixed-step physics

        physics_accumulator += dt

        while physics_accumulator >= physics_step:

            try:

                world_loader.update_physics(physics_step)

            except Exception:

                traceback.print_exc()

            physics_accumulator -= physics_step



        # Throttled RPC update

        now = time.time()

        if rpc_connected and now - globals().get("last_rpc_update", 0) >= 1.0:

            try:

                rpc.update(state="In the darkness")

            except Exception:

                pass

            globals()["last_rpc_update"] = now



        # â”€â”€ All game drawing to renderer (320x180) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

        try:

            cam_x, cam_y = get_cam_target(player)

            world_loader.draw_world(renderer, cam_x, cam_y)

            world_loader.draw_physic_objects(renderer, dt)

            world_loader.draw_black_layer(renderer, cam_x, cam_y)

            world_loader.draw_shadow(renderer)

            # player.draw writes sprite to renderer; death screen to screen

            player.draw(renderer, world_loader, screen)

        except Exception:

            traceback.print_exc()



        # Always blit the live renderer â€” player.py owns the death animation

        # during freeze_frame_active, and the black death screen once self.dead

        blit_renderer_to_screen(screen, renderer)



        # Draw remote players (only when --join)

        # if mp and MP_JOIN_MODE:

        #     try:

        #         mp.draw(renderer, world_loader)

        #     except Exception:

        #         pass



        # Fight updates/draws

        if getattr(player, "active_fight", None) and getattr(player.active_fight, "running", False):

            try:

                player.active_fight.update(dt)

                player.active_fight.draw()

            except Exception:

                traceback.print_exc()

        # FPS counter

        fps = int(clock.get_fps())

        if fps != last_fps_value:

            last_fps_value = fps

            try:

                last_fps_text = fps_font.render(f"FPS: {fps}", True, (255, 0, 0))

            except Exception:

                last_fps_text = None

        world_loader.draw_timer(screen)



        if DEBUG_FORCE_RED_SQUARE:

            pygame.draw.rect(renderer, (255, 0, 0), (10, 10, 50, 50))



        # â”€â”€ Full-res overlays drawn on top of upscaled screen â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

        if last_fps_text:

            try:
                if options['debug'] != 0.0:
                    screen.blit(last_fps_text, (10, 10))
            except Exception:

                pass



        if player.active_cutscene and getattr(player.active_cutscene, "running", False):

            try:

                player.active_cutscene.draw(screen)

            except Exception:

                pass



        if player.active_interactive and getattr(player.active_interactive, "running", False):

            try:

                player.active_interactive.draw(screen)

            except Exception:

                pass



        # Draw debug level warp popup

        if debug_warp_popup.active:

            debug_warp_popup.draw()


        pygame.display.flip()



    # â”€â”€ Cleanup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    # if mp:

    #     try:

    #         mp.stop()

    #     except Exception:

    #         pass



    pygame.quit()

    try:

        rpc.clear()

        rpc.close()

    except Exception:

        pass





if __name__ == "__main__":

    try:

        main()

    except Exception:

        error_text = traceback.format_exc()

        print(error_text)

        try:

            play_error_gif(error_text)

        except Exception:

            show_error_window(error_text)




