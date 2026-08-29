import os
import pygame
import urllib.request


# -----------------------------
# NETWORK / UTILS
# -----------------------------

def get_public_ip():
    try:
        return urllib.request.urlopen("https://api.ipify.org", timeout=2).read().decode("utf-8")
    except:
        return "UNKNOWN"


# -----------------------------
# AUDIO SYSTEM (LOCAL MULTI-TRACK)
# -----------------------------

class AudioManager:
    def __init__(self, folder="songs"):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)

        pygame.mixer.init()
        pygame.mixer.set_num_channels(32)

        self.cache = {}  # id -> file path

    def register(self, song_id, filename):
        path = os.path.join(self.folder, filename)
        self.cache[song_id] = path

    def play_all(self, song_ids):
        for song_id in song_ids:
            path = self.cache.get(song_id)

            if not path:
                print("[AUDIO] Missing mapping:", song_id)
                continue

            if not os.path.exists(path):
                print("[AUDIO] File not found:", path)
                continue

            try:
                sound = pygame.mixer.Sound(path)
                channel = pygame.mixer.find_channel()

                if channel:
                    channel.play(sound)
                else:
                    print("[AUDIO] No free channel for:", song_id)

            except Exception as e:
                print("[AUDIO ERROR]", e)


# -----------------------------
# CUTSCENE
# -----------------------------

class cutscene:
    def __init__(self, player, world, loader):
        self.dialogue_id = "the_end"
        self.player = player
        self.world = world
        self.loader = loader

        self.public_ip = get_public_ip()
        self.font = pygame.font.SysFont("Arial", 24)

        self.audio = AudioManager()

        #  logical track IDs
        self.songs = ["1", "2", "3", "4", "5", "6", "7", "8"]

        #  register local files (MUST EXIST IN /songs)
        for song_id in self.songs:
            self.audio.register(song_id, f"{song_id}.mp3")

        self.preloaded = False
        self.playing = False

    # -----------------------------
    # CUTSCENE START
    # -----------------------------

    def END(self):
        self.preload()



        if not self.playing:

            #  play EVERYTHING at once
            self.audio.play_all(self.songs)

        self.playing = True

        # return "YES"

    # -----------------------------
    # PRELOAD CHECK
    # -----------------------------

    def preload(self):
        if self.preloaded:
            return

        missing = []
        for song_id in self.songs:
            path = self.audio.cache.get(song_id)
            if not path or not os.path.exists(path):
                missing.append(song_id)

        if missing:
            print("[AUDIO] Missing files:")
            for m in missing:
                print(" -", m)

        self.preloaded = True

    # -----------------------------
    # UPDATE
    # -----------------------------

    def update(self, dt):
        pass

    # -----------------------------
    # DRAW
    # -----------------------------

    def draw_front(self, loader, surface):
        pygame.draw.rect(
            surface,
            (0, 0, 0),
            (0, 0, surface.get_width(), surface.get_height())
        )

    def draw_back(self, loader, surface):
        if self.playing:
            pygame.draw.rect(
                surface,
                (0, 0, 0),
                (0, 0, surface.get_width(), surface.get_height())
            )
            text = self.font.render(
                f"IP: {self.public_ip}",
                True,
                (255, 255, 255)
            )

        surface.blit(text, (20, 20))
