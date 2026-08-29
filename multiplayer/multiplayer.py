"""
TWOS Multiplayer Client
-----------------------
Drop-in component used by main.py.

Usage (in main.py):
    from multiplayer.multiplayer import MP

    # After name screen:
    mp = MP(player, room_id="my_room", name=player.name)
    mp.start()                       # spawns background thread

    # In game loop:
    mp.tick(dt)                      # sends state, prunes old players
    mp.draw(renderer, world_loader)  # draws remote players

    # On exit:
    mp.stop()
"""

import os
import json
import threading
import asyncio
import time
import pygame
from assetsLoader import Loader

SERVER_URL  = "wss://dormoticz.duckdns.org:8765"
SEND_HZ     = 60          # state-send rate cap
_TIMEOUT    = 5.0         # seconds of silence before a remote player is pruned


# ---------------------------------------------------------------------------
# Remote-player sprite cache (shared across all MP instances)
# ---------------------------------------------------------------------------
_sprite_cache: dict = {}   # anim_name â†’ [Surface, ...]
_sprite_cache_left: dict = {}

def _load_sprites():
    global _sprite_cache, _sprite_cache_left
    if _sprite_cache:
        return   # already loaded
    sprite_loader = Loader("sprites/Player/animation_frames")
    names = ("Idle", "Walking", "sleep", "Fall_ground")
    for anim in names:
        frames = []
        path   = sprite_loader.load(anim)
        try:
            total = len([n for n in os.listdir(path) if os.path.isfile(os.path.join(path, n))])
        except Exception:
            total = 0
        for i in range(1, total):
            try:
                img = pygame.image.load(sprite_loader.load(f"{anim}/{anim}_{i}.png")).convert_alpha()
            except Exception:
                img = pygame.Surface((40, 80), pygame.SRCALPHA)
                img.fill((255, 100, 255, 160))
            frames.append(img)
        _sprite_cache[anim]      = frames if frames else [_fallback_surface()]
        _sprite_cache_left[anim] = [pygame.transform.flip(f, True, False) for f in _sprite_cache[anim]]

def _fallback_surface():
    s = pygame.Surface((16, 24), pygame.SRCALPHA)
    s.fill((255, 80, 80, 200))
    return s


# ---------------------------------------------------------------------------
# MP class
# ---------------------------------------------------------------------------
class MP:
    def __init__(self, player, room_id: str = "default", name: str = "???", join_mode: bool = False):
        self.player    = player
        self.room_id   = room_id
        self.name      = name
        self.join_mode = join_mode   # True = render + listen; False = send-only ghost
        self.uid       = os.urandom(16).hex()

        # remote players: uid â†’ {x, y, anim, dir, curr_frame, name, _last_seen}
        self._players: dict[str, dict] = {}
        self._lock     = threading.Lock()

        self._running  = False
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

        # send-rate limiter
        self._last_send = 0.0
        self._send_interval = 1.0 / SEND_HZ

        # font for name labels (loaded lazily on first draw)
        self._font = None

    # â”€â”€ public API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def start(self):
        """Spawn the background networking thread."""
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._run_loop, daemon=True, name="MP-net")
        self._thread.start()

    def stop(self):
        """Cleanly shut down networking."""
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=2.0)

    def tick(self, dt: float):
        """Call once per game frame. Sends state and prunes timed-out players."""
        now = time.monotonic()
        if now - self._last_send >= self._send_interval:
            self._last_send = now
            self._enqueue_state()

        # Prune players we haven't heard from in a while
        cutoff = now - _TIMEOUT
        with self._lock:
            dead = [uid for uid, p in self._players.items() if p.get("_last_seen", 0) < cutoff]
            for uid in dead:
                del self._players[uid]
                print(f"[MP] pruned timed-out player {uid[:8]}")

    def draw(self, renderer: pygame.Surface, world_loader):
        """Draw remote players onto the low-res renderer."""
        _load_sprites()
        if self._font is None:
            try:
                self._font = pygame.font.SysFont("Arial", 7)
            except Exception:
                self._font = None

        cam_x = getattr(world_loader, "cam_x", 0)
        cam_y = getattr(world_loader, "cam_y", 0)
        rw, rh = renderer.get_size()

        with self._lock:
            players_snapshot = list(self._players.values())

        my_level = getattr(self.player, "_current_level", 0)

        for p in players_snapshot:
            # --- level filter: skip players on a different level ---
            if p.get("level", 0) != my_level:
                continue

            wx    = p.get("x", 0)
            wy    = p.get("y", 0)
            anim  = p.get("anim", "Idle")
            frame = int(p.get("curr_frame", 0))
            direc = p.get("dir", 0)   # 0=right, 1=left (matches Player.dir)
            name  = str(p.get("name", "???"))[:14]

            # Mirror Player.draw exactly:
            #   world_x / world_y are the top-left of the hitbox area.
            #   feet centre = (wx + hitbox_w/2,  wy + hitbox_h)
            #   We don't have the remote hitbox dims, so use the same
            #   constants the local Player uses: hit_box = Rect(5,0,6,16)
            HITBOX_W = 6
            HITBOX_H = 16
            feet_cx = wx + 5 + HITBOX_W / 2.0   # hitbox_offset_x=0, left=5
            feet_cy = wy +     HITBOX_H           # hitbox_offset_y=0

            sx = round(feet_cx - cam_x)
            sy = round(feet_cy - cam_y)

            # Get sprite frame
            cache = _sprite_cache_left if direc else _sprite_cache
            frames = cache.get(anim) or cache.get("Idle") or [_fallback_surface()]
            img    = frames[frame % len(frames)]

            # blit so sprite's bottom-centre lands on (sx, sy) â€” same as midbottom
            draw_x = sx - img.get_width()  // 2
            draw_y = sy - img.get_height()

            # Skip if well off-screen
            if draw_x > rw + 4 or draw_x + img.get_width()  < -4:
                continue
            if draw_y > rh + 4 or draw_y + img.get_height() < -4:
                continue

            renderer.blit(img, (draw_x, draw_y))

            # Name tag
            if self._font:
                try:
                    label = self._font.render(name, True, (220, 220, 255))
                    lx = sx - label.get_width() // 2
                    ly = draw_y - label.get_height() - 1
                    # Tiny dark shadow
                    shadow = self._font.render(name, True, (20, 20, 40))
                    renderer.blit(shadow, (lx + 1, ly + 1))
                    renderer.blit(label,  (lx,     ly))
                except Exception:
                    pass

    # â”€â”€ internal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _enqueue_state(self):
        """Build state dict and schedule a send on the asyncio loop."""
        p = self.player
        state = {
            "type":       "state",
            "room_id":    self.room_id,
            "uid":        self.uid,
            "name":       self.name,
            "x":          p.world_x,
            "y":          p.world_y,
            "anim":       getattr(p, "curr_animation", "Idle"),
            "curr_frame": getattr(p, "curr_frame",     0),
            "dir":        getattr(p, "dir",            0),
            "level":      getattr(p, "_current_level", 0),
        }
        if self._loop and self._loop.is_running() and hasattr(self, "_send_queue"):
            def _put(q=self._send_queue, s=state):
                # drain any stale packet, then put the fresh one
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    q.put_nowait(s)
                except asyncio.QueueFull:
                    pass
            self._loop.call_soon_threadsafe(_put)

    def _run_loop(self):
        """Background thread: owns an asyncio event loop that keeps the WS alive."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._send_queue: asyncio.Queue = asyncio.Queue(maxsize=1)  # drop stale packets
        try:
            self._loop.run_until_complete(self._network_task())
        finally:
            self._loop.close()

    async def _network_task(self):
        """Connect (with auto-reconnect) and handle messages."""
        import websockets

        while self._running:
            try:
                print(f"[MP] Connecting to {SERVER_URL} ...")
                async with websockets.connect(SERVER_URL, open_timeout=5) as ws:
                    print(f"[MP] Connected! room={self.room_id!r} uid={self.uid[:8]}")

                    # Send join
                    await ws.send(json.dumps({
                        "type":    "join",
                        "room_id": self.room_id,
                        "uid":     self.uid,
                        "name":    self.name,
                    }))

                    # Run sender and receiver concurrently
                    await asyncio.gather(
                        self._sender(ws),
                        self._receiver(ws),
                    )

            except Exception as exc:
                print(f"[MP] Connection error: {exc}  â€” retrying in 3s")
                with self._lock:
                    self._players.clear()   # stale on disconnect
                if self._running:
                    await asyncio.sleep(3)

    async def _sender(self, ws):
        """Forward queued state packets to the server."""
        while self._running:
            try:
                state = await asyncio.wait_for(self._send_queue.get(), timeout=1.0)
                await ws.send(json.dumps(state))
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

    async def _receiver(self, ws):
        """Handle incoming messages from the server."""
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            t = msg.get("type")

            # Ghost mode (no --join): drain socket but ignore everything.
            # We still need to read so the TCP buffer doesn't back up.
            if not self.join_mode:
                continue

            if t == "room_state":
                # Full dump of current occupants when we first join
                with self._lock:
                    for p in msg.get("players", []):
                        uid = p.get("uid")
                        if uid and uid != self.uid:
                            p["_last_seen"] = time.monotonic()
                            self._players[uid] = p
                print(f"[MP] Room has {len(msg.get('players', []))} existing players")

            elif t == "player_join":
                uid  = msg.get("uid")
                name = msg.get("name", "???")
                if uid and uid != self.uid:
                    with self._lock:
                        if uid not in self._players:
                            self._players[uid] = {"name": name, "_last_seen": time.monotonic()}
                    print(f"[MP] {name!r} joined")

            elif t == "player_state":
                uid = msg.get("uid")
                if uid and uid != self.uid:
                    with self._lock:
                        if uid in self._players:
                            self._players[uid].update(msg)
                            self._players[uid]["_last_seen"] = time.monotonic()
                        else:
                            # First state packet before join message (race)
                            msg["_last_seen"] = time.monotonic()
                            self._players[uid] = msg

            elif t == "player_leave":
                uid = msg.get("uid")
                with self._lock:
                    name = self._players.pop(uid, {}).get("name", uid[:8] if uid else "?")
                print(f"[MP] {name!r} left")

        # socket closed â†’ raise so _network_task reconnects
        raise websockets.exceptions.ConnectionClosed(None, None)

