import ctypes
import math
import threading
import time
from ctypes import wintypes

import keyboard

DIRS = {"w": (0, 1), "s": (0, -1), "a": (-1, 0), "d": (1, 0)}
SCAN = {"w": 0x11, "a": 0x1E, "s": 0x1F, "d": 0x20}
TRIGGER_KEY = "t"
QUIT_KEY = "o"
LANE_WIDTH = 0.1
PASS_PAUSE = 0.2
MOVE_BIAS = 0.008
SNAP = 0.0

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
INPUT_KEYBOARD = 1

winmm = ctypes.windll.winmm

pressed = set()
pos = [0.0, 0.0]
bounds = [0.0, 0.0, 0.0, 0.0]
last = None
locked = False
trigger = threading.Event()
quit_event = threading.Event()


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def send_key(name, down):
    flags = KEYEVENTF_SCANCODE
    if not down:
        flags |= KEYEVENTF_KEYUP
    inp = INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=KEYBDINPUT(0, SCAN[name], flags, 0, None)))
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def release_all():
    for k in SCAN:
        send_key(k, False)


def advance(now):
    global last
    if last is None:
        last = now
        return
    dt = now - last
    last = now
    vx = sum(DIRS[k][0] for k in pressed)
    vy = sum(DIRS[k][1] for k in pressed)
    n = math.hypot(vx, vy)
    if not n:
        return
    pos[0] += vx / n * dt
    pos[1] += vy / n * dt
    bounds[0] = min(bounds[0], pos[0])
    bounds[1] = max(bounds[1], pos[0])
    bounds[2] = min(bounds[2], pos[1])
    bounds[3] = max(bounds[3], pos[1])


def on_key(e):
    if e.event_type == "down" and e.name == QUIT_KEY:
        quit_event.set()
        return
    if locked:
        return
    now = time.perf_counter()
    if e.event_type == "down" and e.name == TRIGGER_KEY:
        advance(now)
        trigger.set()
        return
    if e.name not in DIRS:
        return
    if e.event_type == "down":
        if e.name in pressed:
            return
        advance(now)
        pressed.add(e.name)
    else:
        advance(now)
        pressed.discard(e.name)


def vec(axis, d):
    return (d, 0.0) if axis == 0 else (0.0, d)


def sweep(start, box, axis):
    lo = (box[0], box[2])
    hi = (box[1], box[3])
    stack = 1 - axis
    run_len = hi[axis] - lo[axis]
    stack_len = hi[stack] - lo[stack]
    rs = 1 if start[axis] == lo[axis] else -1
    ss = 1 if start[stack] == lo[stack] else -1
    lanes = math.ceil(stack_len / LANE_WIDTH) + 1
    step = stack_len / (lanes - 1) if lanes > 1 else 0.0
    moves = []
    for i in range(lanes):
        moves.append(vec(axis, rs * run_len))
        rs = -rs
        if i < lanes - 1:
            moves.append(vec(stack, ss * step))
    return moves


def plan(cur, box):
    x0, x1, y0, y1 = box
    corners = [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
    start = min(corners, key=lambda c: abs(c[0] - cur[0]) + abs(c[1] - cur[1]))
    best = None
    for axis in (0, 1):
        moves = sweep(start, box, axis)
        cost = sum(abs(dx) + abs(dy) for dx, dy in moves)
        if best is None or cost < best[0]:
            best = (cost, moves)
    end = (start[0] + sum(m[0] for m in best[1]), start[1] + sum(m[1] for m in best[1]))
    return best[1], end


def wait_until(t):
    while not quit_event.is_set():
        rem = t - time.perf_counter()
        if rem <= 0:
            return
        if rem > 0.003:
            time.sleep(0.001)


def move(dx, dy, t):
    duration = abs(dx) + abs(dy)
    if duration < 0.001:
        return t
    if dx > 0:
        key = "d"
    elif dx < 0:
        key = "a"
    elif dy > 0:
        key = "w"
    else:
        key = "s"
    send_key(key, True)
    t += duration
    wait_until(t - MOVE_BIAS)
    send_key(key, False)
    wait_until(t)
    return t


def snap(cur, box):
    x0, x1, y0, y1 = box
    keys = []
    if abs(cur[0] - x1) < 0.01:
        keys.append("d")
    elif abs(cur[0] - x0) < 0.01:
        keys.append("a")
    if abs(cur[1] - y1) < 0.01:
        keys.append("w")
    elif abs(cur[1] - y0) < 0.01:
        keys.append("s")
    for k in keys:
        send_key(k, True)
    wait_until(time.perf_counter() + SNAP)
    for k in keys:
        send_key(k, False)


def main():
    global locked
    keyboard.hook(on_key)
    print(f"Walk out your box with WASD. '{TRIGGER_KEY.upper()}' = start filling, '{QUIT_KEY.upper()}' = quit.")

    while not trigger.is_set() and not quit_event.is_set():
        time.sleep(0.01)
    locked = True
    if quit_event.is_set():
        keyboard.unhook_all()
        return

    release_all()
    box = tuple(bounds)
    if not any(box):
        print("Nothing recorded.")
        keyboard.unhook_all()
        return

    winmm.timeBeginPeriod(1)
    cur = (pos[0], pos[1])
    n = 1
    t = time.perf_counter()
    while not quit_event.is_set():
        moves, cur = plan(cur, box)
        print(f"Fill {n}")
        for dx, dy in moves:
            t = move(dx, dy, t)
            if quit_event.is_set():
                break
        if SNAP > 0 and not quit_event.is_set():
            snap(cur, box)
            t = time.perf_counter()
        n += 1
        t += PASS_PAUSE
        wait_until(t)

    release_all()
    winmm.timeEndPeriod(1)
    keyboard.unhook_all()
    print("Stopped.")


if __name__ == "__main__":
    main()