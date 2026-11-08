import asyncio
import gc
import json
import math
import os
import sys
import threading
import time
import traceback
from pathlib import Path

import pygame

from assetsLoader import Loader

# pygbag (the pygame -> web/WASM exporter) sets sys.platform to "emscripten".
# Used to disable anything desktop/Windows-only when running in the browser.
WEB_BUILD = sys.platform == "emscripten"
IS_WINDOWS = sys.platform.startswith("win")

if not WEB_BUILD:
    import urllib.error
    import urllib.request

    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, scrolledtext, ttk
    except Exception:
        tk = None

    if IS_WINDOWS:
        try:
            import ctypes
        except Exception:
            ctypes = None
    else:
        ctypes = None

    try:
        from pypresence import Presence
    except Exception:
        Presence = None
else:
    tk = None
    ctypes = None
    Presence = None

gc.collect()

BROADCAST_SERVER_URL = "http://dormoticz.duckdns.org:5050/"
BROADCAST_POLL_INTERVAL = 10

MB_OK = 0x00000000
MB_ICONINFORMATION = 0x00000040
MB_ICONWARNING = 0x00000030
MB_ICONERROR = 0x00000010
MB_TOPMOST = 0x00040000


def _show_windows_msgbox(title: str, text: str, icon: int = MB_ICONINFORMATION):
    """Show a native Windows MessageBox (non-blocking via thread). No-op off Windows/web."""
    if WEB_BUILD or not IS_WINDOWS or ctypes is None:
        print(f"[{title}] {text}")
        return

    def _run():
        try:
            ctypes.windll.user32.MessageBoxW(
                0, str(text), str(title), MB_OK | icon | MB_TOPMOST
            )
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()


def _broadcast_poll_loop():
    """Poll the broadcast server and pop a MessageBox for any unseen message."""
    last_seen_id = 0

    while True:
        try:
            url = f"{BROADCAST_SERVER_URL}/poll?since={last_seen_id}"
            req = urllib.request.Request(url, headers={"User-Agent": "TWoS-Client/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            for msg in data.get("messages", []):
                msg_id = msg.get("id", 0)
                msg_text = msg.get("text", "")
                if msg_id > last_seen_id:
                    last_seen_id = msg_id
                    _show_windows_msgbox(
                        "Message from the developer", msg_text, MB_ICONINFORMATION
                    )

        except urllib.error.URLError:
            pass
        except Exception:
            pass

        time.sleep(BROADCAST_POLL_INTERVAL)


def start_broadcast_client():
    """Start the background broadcast polling thread. Disabled on web."""
    if WEB_BUILD:
        return
    t = threading.Thread(target=_broadcast_poll_loop, daemon=True)
    t.name = "BroadcastClient"
    t.start()


try:
    from multiplayer.multiplayer import MP as _MP

    MULTIPLAYER_AVAILABLE = True

except Exception:
    _MP = None

    MULTIPLAYER_AVAILABLE = False


# --join flag: full multiplayer (render + listen).
# Without it: still connects + sends, but never draws/receives others.
MP_JOIN_MODE = "--join" in sys.argv

client_id = "1441698591579312168"

rpc = Presence(client_id) if (Presence is not None and not WEB_BUILD) else None

rpc_connected = False

SCREEN_RESOLUTION = (1280, 720)
MINI_RESOLUTION = (320, 180)
FPS = 60  # 0 for uncapped

OPTIONS_FILE = os.path.join(os.path.expanduser("~"), "TWOSFILES", "options.json")

BASE_DIR = Path(__file__).parent
CACHE_DIR = BASE_DIR / "cache"

LOADING_SCALE = 10
loading_font = None

DEBUG_FORCE_RED_SQUARE = False


def rpc_background_connect():
    global rpc_connected

    if rpc is None:
        return

    try:
        rpc.connect()
        rpc_connected = True
    except Exception:
        pass


if not WEB_BUILD and rpc is not None:
    threading.Thread(target=rpc_background_connect, daemon=True).start()


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


def catch_mouse(X):
    if X:
        pygame.mouse.set_visible(False)
        pygame.mouse.set_pos((1280 / 2, 720 / 2))
    else:
        pygame.mouse.set_visible(True)


def save_surface_cache(filename, surface):
    CACHE_DIR.mkdir(exist_ok=True)

    pygame.image.save(surface, str(CACHE_DIR / filename))


def load_surface_cache(filename):
    path = CACHE_DIR / filename

    if path.exists():
        return pygame.image.load(str(path)).convert_alpha()

    return None


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
    options_dir = os.path.dirname(options_path)
    if options_dir:
        os.makedirs(options_dir, exist_ok=True)

    with open(options_path, "w", encoding="utf-8") as f:
        json.dump(options, f, indent=4)


def init_pygame(options):
    os.environ["SDL_RENDER_VSYNC"] = "0"
    os.environ["SDL_VIDEO_X11_FORCE_EGL"] = "0"

    pygame.init()
    pygame.mixer.init()

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
    pygame.mouse.set_visible(False)
    renderer = pygame.Surface(MINI_RESOLUTION)

    try:
        icon_loader = Loader("icon")
        icon_path = icon_loader.load("lantern.png")

        if icon_path and os.path.exists(icon_path):
            icon_surface = pygame.image.load(icon_path).convert_alpha()
            pygame.display.set_icon(icon_surface)

    except Exception:
        pass

    pygame.mixer.music.set_volume(options.get("master_volume", 0.5))

    return screen, fps_font, renderer


def draw_loading_screen_old(surface, progress, text="Loading..."):
    surface.fill((30, 30, 30))

    font = pygame.font.SysFont("Arial", 50, bold=True)
    label = font.render(text, True, (255, 200, 50))

    surface.blit(label, (surface.get_width() // 2 - label.get_width() // 2, 140))

    bar_w, bar_h = 500, 40
    x = surface.get_width() // 2 - bar_w // 2
    y = 220

    pygame.draw.rect(surface, (100, 100, 100), (x, y, bar_w, bar_h), border_radius=10)

    fill_w = max(0, int(bar_w * max(0.0, min(1.0, progress))))

    if fill_w > 4:
        pygame.draw.rect(
            surface,
            (255, 200, 50),
            (x + 2, y + 2, fill_w - 4, bar_h - 4),
            border_radius=10,
        )

    dot_font = pygame.font.SysFont("Arial", 28)
    dot_label = dot_font.render("." * (int(time.time() * 2) % 4), True, (255, 200, 50))

    surface.blit(
        dot_label, (surface.get_width() // 2 + label.get_width() // 2 + 10, 140)
    )


def draw_loading_screen(
    surface, progress, text="LOADING...", inside_img=None, outline_img=None
):
    global loading_font

    progress = max(0.0, min(1.0, progress))

    surface.fill((20, 35, 41))

    if loading_font is None:
        try:
            fl = Loader("ui/menu")
            fp = fl.load("loadmenufont.ttf")

            if fp and os.path.exists(fp):
                loading_font = pygame.font.Font(fp, 54)
            else:
                loading_font = pygame.font.SysFont("Arial", 32, bold=True)

        except Exception:
            loading_font = pygame.font.SysFont("Arial", 32, bold=True)

    label = loading_font.render(text, True, (230, 230, 230))

    surface.blit(label, label.get_rect(center=(surface.get_width() // 2, 80)))

    if not inside_img or not outline_img:
        draw_loading_screen_old(surface, progress, text)
        return

    out_w, out_h = outline_img.get_size()
    in_w, in_h = inside_img.get_size()

    bar_x = surface.get_width() // 2 - out_w // 2
    bar_y = surface.get_height() // 2 - out_h // 2 + 8

    fill_w = int(in_w * progress)

    surface.blit(outline_img, (bar_x, bar_y))

    if fill_w > 0:
        source_rect = pygame.Rect(0, 0, fill_w, in_h)

        surface.blit(
            inside_img,
            (bar_x + 4 * LOADING_SCALE, bar_y + 8 * LOADING_SCALE),
            source_rect,
        )


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

    loader = Loader("ui/error")
    gif_path = loader.load("eepy.gif")
    music_path = loader.load("thatstoobad.mp3")

    try:
        if music_path and os.path.exists(music_path):
            _pg.mixer.music.load(music_path)
            _pg.mixer.music.play(-1)
    except Exception:
        pass

    gif = Image.open(gif_path)

    frames = []
    durations = []

    for frame in ImageSequence.Iterator(gif):
        frame = frame.convert("RGBA")
        data = frame.tobytes()
        py_frame = _pg.image.fromstring(data, frame.size, frame.mode)

        frames.append(py_frame)
        durations.append(frame.info.get("duration", 100))

    clock = _pg.time.Clock()

    frame_index = 0
    running = True
    timer = 0

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


ERROR_ICON = "[X]"


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

    style.configure("TFrame", background="#1e1e1e")
    style.configure(
        "TLabel", background="#1e1e1e", foreground="#ffffff", font=("Segoe UI", 11)
    )
    style.configure("Header.TLabel", font=("Segoe UI", 15, "bold"))
    style.configure(
        "TButton",
        background="#3c3c3c",
        foreground="#ffffff",
        font=("Segoe UI", 10),
        padding=6,
    )
    style.map("TButton", background=[("active", "#505050")])

    frame = ttk.Frame(root)
    frame.pack(fill="both", expand=True, padx=15, pady=15)

    header = ttk.Label(
        frame, text=f"{ERROR_ICON} I AM BAD AT CODING", style="Header.TLabel"
    )
    header.pack(anchor="w", pady=(0, 10))

    text_box = scrolledtext.ScrolledText(
        frame,
        wrap=tk.WORD,
        font=("Consolas", 11),
        background="#252526",
        foreground="#d4d4d4",
        insertbackground="white",
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
            initialfile="error_log.txt",
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
        )

        if filename:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(error_text)

            messagebox.showinfo("Saved", f"Error log saved to:\n{filename}")

    ttk.Button(button_frame, text="Copy", command=copy_to_clipboard).pack(
        side="left", padx=5
    )
    ttk.Button(button_frame, text="Save", command=save_error).pack(side="left", padx=5)

    root.mainloop()


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
    cx = player.world_x + player.hitbox_offset_x + player.hit_box.width / 2.0
    cy = player.world_y + player.hitbox_offset_y + player.hit_box.height / 2.0

    return cx, cy


def get_available_levels():
    """Dynamically get available levels from worlds directory."""
    import os

    loader = Loader("worlds").load(".")
    worlds_dir = loader
    if not os.path.exists(worlds_dir):
        return []

    levels = []
    for item in os.listdir(worlds_dir):
        item_path = os.path.join(worlds_dir, item)
        if os.path.isdir(item_path) and item.isdigit():
            levels.append(item)

    return sorted(levels, key=lambda x: int(x))


def _get_available_modules(directory):
    """Return the importable .py module names from a game content directory."""
    content_dir = Loader(directory).load(".")
    if not os.path.exists(content_dir):
        return []

    ignore = {"__init__.py", "loader.py"}
    modules = []
    for item in os.listdir(content_dir):
        item_path = os.path.join(content_dir, item)
        if not os.path.isfile(item_path):
            continue
        if not item.endswith(".py") or item in ignore or item.startswith("_"):
            continue
        modules.append(item[:-3])

    return sorted(modules)


def get_available_cutscenes():
    """Dynamically get available cutscenes from the cutscenes directory."""
    return _get_available_modules("cutscenes")


def get_available_interactables():
    """Dynamically get available interactables from the interactables directory."""
    return _get_available_modules("interactables")


class DebugMenu:
    """A searchable list popup used by the in-game debug tools."""

    MAX_VISIBLE = 8

    def __init__(self, screen, title):
        self.screen = screen
        self.title = title
        self.active = False
        self.selected_index = 0
        self.items = []
        self.search = ""
        self.scroll_offset = 0
        self.font = pygame.font.SysFont("Arial", 20, bold=True)
        self.small_font = pygame.font.SysFont("Arial", 16)

    def set_items(self, item_list):
        """Set the selectable items."""
        self.items = list(item_list) if item_list else []
        self.selected_index = 0
        self.scroll_offset = 0

    def set_levels(self, level_list):
        """Backwards-compatible alias for set_items."""
        self.set_items(level_list)

    def open(self):
        self.active = True
        self.search = ""
        self.selected_index = 0
        self.scroll_offset = 0

    def close(self):
        self.active = False

    def _filtered_items(self):
        if not self.search:
            return self.items
        term = self.search.lower()
        return [item for item in self.items if term in item.lower()]

    def _selected_item(self):
        filtered = self._filtered_items()
        if not filtered:
            return None
        self.selected_index %= len(filtered)
        return filtered[self.selected_index]

    def handle_event(self, event):
        """Handle a pygame event. Returns the chosen item when selected."""
        if not self.active or event.type != pygame.KEYDOWN:
            return None

        if event.key == pygame.K_ESCAPE:
            self.close()
            return None

        filtered = self._filtered_items()

        if event.key == pygame.K_RETURN:
            item = self._selected_item()
            if item:
                self.close()
                return item
            return None

        if event.key == pygame.K_UP:
            if filtered:
                self.selected_index = (self.selected_index - 1) % len(filtered)
            return None

        if event.key == pygame.K_DOWN:
            if filtered:
                self.selected_index = (self.selected_index + 1) % len(filtered)
            return None

        if event.key == pygame.K_BACKSPACE:
            self.search = self.search[:-1]
            self.selected_index = 0
            self.scroll_offset = 0
            return None

        if event.unicode and event.unicode.isprintable():
            self.search += event.unicode
            self.selected_index = 0
            self.scroll_offset = 0

        return None

    def draw(self):
        """Draw the debug menu popup on screen."""
        if not self.active:
            return

        filtered = self._filtered_items()
        if filtered:
            self.selected_index %= len(filtered)
            if self.selected_index < self.scroll_offset:
                self.scroll_offset = self.selected_index
            elif self.selected_index >= self.scroll_offset + self.MAX_VISIBLE:
                self.scroll_offset = self.selected_index - self.MAX_VISIBLE + 1
            self.scroll_offset = max(
                0, min(self.scroll_offset, len(filtered) - self.MAX_VISIBLE)
            )
        else:
            self.selected_index = 0
            self.scroll_offset = 0

        overlay = pygame.Surface(self.screen.get_size())
        overlay.set_alpha(200)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))

        popup_width, popup_height = 540, 440
        popup_x = self.screen.get_width() // 2 - popup_width // 2
        popup_y = self.screen.get_height() // 2 - popup_height // 2

        pygame.draw.rect(
            self.screen, (50, 50, 50), (popup_x, popup_y, popup_width, popup_height)
        )
        pygame.draw.rect(
            self.screen,
            (200, 200, 200),
            (popup_x, popup_y, popup_width, popup_height),
            3,
        )

        title = self.font.render(self.title, True, (255, 200, 50))
        self.screen.blit(
            title, (popup_x + popup_width // 2 - title.get_width() // 2, popup_y + 15)
        )

        search_rect = (popup_x + 15, popup_y + 50, popup_width - 30, 30)
        pygame.draw.rect(self.screen, (30, 30, 30), search_rect)
        pygame.draw.rect(self.screen, (120, 120, 120), search_rect, 2)

        search_text = f"Search: {self.search}"
        if not self.search:
            search_text = "Search: (type to filter)"
        search_color = (255, 255, 255) if self.search else (120, 120, 120)
        search_surface = self.small_font.render(search_text, True, search_color)
        self.screen.blit(search_surface, (search_rect[0] + 8, search_rect[1] + 6))

        count_text = self.small_font.render(
            f"{len(filtered)}/{len(self.items)}", True, (150, 150, 150)
        )
        self.screen.blit(
            count_text,
            (
                search_rect[0] + search_rect[2] - count_text.get_width() - 8,
                search_rect[1] + 6,
            ),
        )

        y_offset = popup_y + 95
        if not filtered:
            no_match = self.small_font.render("No matches", True, (150, 150, 150))
            self.screen.blit(no_match, (popup_x + 20, y_offset))
        else:
            visible_items = filtered[
                self.scroll_offset : self.scroll_offset + self.MAX_VISIBLE
            ]
            for row, item in enumerate(visible_items):
                index = self.scroll_offset + row
                if index == self.selected_index:
                    color = (255, 255, 0)
                    pygame.draw.rect(
                        self.screen,
                        (100, 100, 0),
                        (popup_x + 10, y_offset - 5, popup_width - 20, 25),
                    )
                    text = self.font.render(f"> {item}", True, color)
                else:
                    color = (200, 200, 200)
                    text = self.small_font.render(f"  {item}", True, color)

                self.screen.blit(text, (popup_x + 20, y_offset))
                y_offset += 28

        instructions = [
            "TYPE: Search",
            "UP/DOWN: Navigate",
            "ENTER: Select",
            "ESC: Cancel",
        ]
        inst_y = popup_y + popup_height - 95
        for inst in instructions:
            inst_text = self.small_font.render(inst, True, (150, 150, 150))
            self.screen.blit(inst_text, (popup_x + 20, inst_y))
            inst_y += 20


# Kept for backwards compatibility with any external references.
DebugLevelWarp = DebugMenu


def start_debug_cutscene(player, world, cutscene_id):
    """Start a cutscene directly from the debug menu."""
    try:
        import cutscenes.loader as CutsceneLoaderModule

        player.active_cutscene = None
        player.active_interactive = None

        player.active_cutscene = CutsceneLoaderModule.CutsceneLoader()
        player.curr_animation = "Idle"
        player.active_cutscene.world = world
        player.active_cutscene.event = getattr(player, "event", None)
        player.active_cutscene.player = player
        player.active_cutscene.load(cutscene_id, getattr(player, "joystick", None))
        player.active_cutscene.trigger_idx = None

        if player.active_cutscene.module is None:
            player.active_cutscene = None
            player.incutscene = False
            return

        player.incutscene = True
        print(f"[DEBUG] Started cutscene: {cutscene_id}")
    except Exception as e:
        print(f"Error starting cutscene: {e}")


def start_debug_interactable(player, world, interactable_id):
    """Start an interactable directly from the debug menu."""
    try:
        import interactables.loader as InteractableModule

        player.active_cutscene = None
        player.active_interactive = None

        player.active_interactive = InteractableModule.Interactable()
        player.curr_animation = "Idle"
        player.active_interactive.world = world
        player.active_interactive.event = getattr(player, "event", None)
        player.active_interactive.player = player
        player.active_interactive.load(
            interactable_id, getattr(player, "joystick", None)
        )
        player.active_interactive.trigger_idx = None

        if player.active_interactive.module is None:
            player.active_interactive = None
            return

        print(f"[DEBUG] Started interactable: {interactable_id}")
    except Exception as e:
        print(f"Error starting interactable: {e}")


async def main():
    global loading_font, rpc_connected

    options = load_options()

    screen, fps_font, renderer = init_pygame(options)

    catch_mouse(True)

    start_broadcast_client()

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
    bar_image = safe_load_image(bar_path)

    if loading_image:
        try:
            loading_image = pygame.transform.scale(
                loading_image,
                (
                    int(loading_image.get_width() * LOADING_SCALE),
                    int(loading_image.get_height() * LOADING_SCALE),
                ),
            )
        except Exception:
            pass

    if bar_image:
        try:
            bar_image = pygame.transform.scale(
                bar_image,
                (
                    int(bar_image.get_width() * LOADING_SCALE),
                    int(bar_image.get_height() * LOADING_SCALE),
                ),
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

    await asyncio.sleep(0.12)

    try:
        draw_loading_screen(screen, 0.15, "LOADING...", loading_image, bar_image)
        pygame.display.flip()
    except Exception:
        pass

    clock = pygame.time.Clock()

    dt = clock.tick(FPS) / 1000.0
    dt = min(dt, 0.125)

    try:
        from ui.menu import saymyname
        from ui.menu.menu import Menu, save_options

    except Exception:
        Menu = None
        save_options = lambda x: None
        saymyname = None

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
        player = PlayerModule.Player(screen=screen)
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

    world_data = load_json_cache("world.json")

    try:
        world_loader = WorldModule(MINI_RESOLUTION, player)
        fight_loader = FightModule.Fight(renderer, screen, player, world_loader)
    except Exception as e:
        print(e)

    if not world_data:
        save_json_cache("world.json", {"dummy": True})

    try:
        draw_loading_screen(screen, 1.0, "READY", loading_image, bar_image)
        pygame.display.flip()
    except Exception:
        pass

    await asyncio.sleep(0.3)

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

    if name_obj:
        try:
            name_obj.draw(dt)

            if getattr(name_obj, "chara_name", "") == "LEBREAH" and player:
                player.lebreah = True
                player.refresh_animation()

            player.name = name_obj.chara_name
            try:
                player.true_name = os.getlogin()
            except Exception:
                # os.getlogin() fails without a controlling terminal and doesn't exist on web.
                player.true_name = (
                    os.environ.get("USERNAME") or os.environ.get("USER") or "Player"
                )
            player.maker_name = name_obj.creator_name

        except Exception:
            pass

    if player is None or world_loader is None:
        error_msg = "Critical modules failed to load (player or world). Check imports."

        print(error_msg)

        if not (WEB_BUILD or tk is None):
            show_error_window(error_msg)

        return

    running = True

    last_fps_value = -1
    last_fps_text = None

    physics_accumulator = 0.0
    physics_step = 1.0 / 60.0

    debug_level_menu = DebugMenu(screen, "DEBUG: SELECT LEVEL")
    debug_cutscene_menu = DebugMenu(screen, "DEBUG: SELECT CUTSCENE")
    debug_interactable_menu = DebugMenu(screen, "DEBUG: SELECT INTERACTABLE")
    debug_menus = [
        debug_level_menu,
        debug_cutscene_menu,
        debug_interactable_menu,
    ]

    escape_timer = 0
    escape_active = False

    dark_overlay = pygame.Surface(MINI_RESOLUTION, pygame.SRCALPHA)
    dark_overlay_big = pygame.Surface(SCREEN_RESOLUTION, pygame.SRCALPHA)

    while running:
        dt = clock.tick(FPS) / 1000.0
        dt = min(dt, 1 / 30)

        if dt > 0.2:
            dt = 0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                debug_menu_active = any(menu.active for menu in debug_menus)
                debug_enabled = options.get("debug", 0.0) > 0.0

                if debug_enabled and not debug_menu_active:
                    if event.key == pygame.K_q:
                        debug_level_menu.set_items(get_available_levels())
                        debug_level_menu.open()
                        continue
                    elif event.key == pygame.K_c:
                        debug_cutscene_menu.set_items(get_available_cutscenes())
                        debug_cutscene_menu.open()
                        continue
                    elif event.key == pygame.K_i:
                        debug_interactable_menu.set_items(
                            get_available_interactables()
                        )
                        debug_interactable_menu.open()
                        continue

                for menu in debug_menus:
                    if not menu.active:
                        continue

                    selected = menu.handle_event(event)
                    if selected is None:
                        break

                    if menu is debug_level_menu:
                        try:
                            world_loader.change_level(selected, player)
                            print(f"[DEBUG] Warped to level: {selected}")
                        except Exception as e:
                            print(f"Error warping to level: {e}")
                    elif menu is debug_cutscene_menu:
                        start_debug_cutscene(player, world_loader, selected)
                    elif menu is debug_interactable_menu:
                        start_debug_interactable(player, world_loader, selected)
                    break

        debug_ui_open = any(menu.active for menu in debug_menus)

        keys = pygame.key.get_pressed()

        if keys[pygame.K_ESCAPE] and not debug_ui_open:
            escape_timer += dt
            escape_active = True
            if escape_timer >= 1.5:
                running = False
        else:
            escape_timer = 0.0
            escape_active = False

        renderer.fill((0, 0, 0))

        if not debug_ui_open:
            try:
                player.update(
                    world_loader, renderer, dt, 1.0, player, fight_loader=fight_loader
                )
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
        else:
            physics_accumulator = 0.0

        now = time.time()

        if rpc_connected and now - globals().get("last_rpc_update", 0) >= 1.0:
            try:
                rpc.update(state="In the darkness")
            except Exception:
                pass

            globals()["last_rpc_update"] = now

        # Game drawing goes to the 320x180 renderer
        cam_x, cam_y = get_cam_target(player)

        world_loader.draw_world(screen, renderer, cam_x, cam_y)

        world_loader.draw_physic_objects(renderer, dt)

        player.draw(renderer, world_loader, screen)

        blit_renderer_to_screen(screen, renderer)

        if (
            player.active_cutscene
            and player.active_cutscene.module
            and hasattr(player.active_cutscene.module, "draw_before_blackrect")
        ):
            try:
                player.active_cutscene.module.draw_before_blackrect(
                    player.active_cutscene, screen
                )
            except Exception as e:
                print(f"[CutsceneLoader] Error in cutscene draw: {e}")

        dark_overlay.fill((0, 0, 0, 0))
        world_loader.draw_black_layer(dark_overlay, cam_x, cam_y)
        world_loader.draw_shadow(dark_overlay)
        pygame.transform.scale(dark_overlay, SCREEN_RESOLUTION, dark_overlay_big)
        screen.blit(dark_overlay_big, (0, 0))

        if getattr(player, "active_fight", None) and getattr(
            player.active_fight, "running", False
        ):
            try:
                player.active_fight.update(dt)
                if getattr(player, "active_fight", None) and getattr(
                    player.active_fight, "running", False
                ):
                    player.active_fight.draw()

            except Exception:
                traceback.print_exc()

        fps = int(clock.get_fps())

        if fps != last_fps_value:
            last_fps_value = fps

            try:
                last_fps_text = fps_font.render(f"FPS: {fps}", True, (255, 0, 0))
            except Exception:
                last_fps_text = None

        escape_text = loading_font.render(
            f"EXITING{'.' * math.ceil(escape_timer)}", True, (255, 255, 255)
        )
        if escape_active:
            screen.blit(escape_text, (10, 10))

        world_loader.draw_timer(screen)

        if DEBUG_FORCE_RED_SQUARE:
            pygame.draw.rect(renderer, (255, 0, 0), (10, 10, 50, 50))

        # Full-res overlays drawn on top of the upscaled screen
        if last_fps_text:
            try:
                if options["debug"] != 0.0:
                    screen.blit(last_fps_text, (10, 10))
            except Exception:
                pass

        if player.active_cutscene and getattr(player.active_cutscene, "running", False):
            try:
                player.active_cutscene.draw(screen)
            except Exception:
                pass

        if player.active_interactive and getattr(
            player.active_interactive, "running", False
        ):
            try:
                player.active_interactive.draw(screen)
            except Exception:
                pass

        if player.midgamemenu.showing:
            player.midgamemenu.txt_engine.draw(
                500, 100, surface=player.midgamemenu.true_screen, size=28
            )
            player.midgamemenu.txt_engine1.draw(
                420, 300, surface=player.midgamemenu.true_screen, size=14
            )

        for menu in debug_menus:
            if menu.active:
                menu.draw()

        pygame.display.flip()

    pygame.quit()

    if rpc is not None:
        try:
            rpc.clear()
            rpc.close()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())

    except Exception:
        error_text = traceback.format_exc()

        print(error_text)

        if not WEB_BUILD:
            try:
                play_error_gif(error_text)

            except Exception:
                if tk is not None:
                    show_error_window(error_text)