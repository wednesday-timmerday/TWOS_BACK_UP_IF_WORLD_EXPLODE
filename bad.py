import argparse, sys, time, unicodedata, pickle, os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

CW, CH = 16, 12

ap = argparse.ArgumentParser()
ap.add_argument("video")
ap.add_argument("--font", nargs="+", default=[r"C:\Windows\Fonts\arial.ttf"])
ap.add_argument("--cols", type=int, default=100)
ap.add_argument("--step", type=int, default=1)
ap.add_argument("--cache", default="badapple_frames.pkl")
ap.add_argument("--thresh", type=int, default=128)
ap.add_argument("--export")
ap.add_argument("--scale", type=int, default=2)
args = ap.parse_args()


def usable(cp):
    c = chr(cp)
    cat = unicodedata.category(c)
    if cat[0] in "CMZ" or cat == "Cn":
        return False
    return unicodedata.east_asian_width(c) in ("N", "Na", "A", "H")


def build_glyphs():
    seen = {}
    for path in args.font:
        cmap = TTFont(path, lazy=True).getBestCmap()
        font = ImageFont.truetype(path, 16)
        for cp in cmap:
            if not usable(cp):
                continue
            img = Image.new("L", (8, 16), 0)
            ImageDraw.Draw(img).text((0, 0), chr(cp), fill=255, font=font)
            arr = np.asarray(img, dtype=np.uint8)
            if arr.max() == 0 and cp != 32:
                continue
            small = cv2.resize(arr, (CW, CH), interpolation=cv2.INTER_AREA)
            key = small.tobytes()
            if key not in seen:
                seen[key] = (chr(cp), small)
    chars = [v[0] for v in seen.values()]
    mats = np.stack([v[1].reshape(-1) for v in seen.values()]).astype(np.float32) / 255
    return chars, mats


def render_all():
    chars, G = build_glyphs()
    print(f"{len(chars)} distinct glyphs", file=sys.stderr)
    chars = np.array(chars)
    bias = (G * G).sum(1)
    GT = G.T.copy()
    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    ok, frame = cap.read()
    h, w = frame.shape[:2]
    cols = args.cols
    rows = max(1, round(cols * (h / w) * 0.5))
    frames = []
    i = 0
    prev = None
    idx = np.zeros(rows * cols, dtype=np.int64)
    while ok:
        if i % args.step == 0:
            g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            g = cv2.resize(g, (cols * CW, rows * CH), interpolation=cv2.INTER_AREA)
            g = (g > args.thresh).astype(np.float32)
            B = g.reshape(rows, CH, cols, CW).transpose(0, 2, 1, 3).reshape(rows * cols, CW * CH)
            changed = np.arange(len(B)) if prev is None else np.flatnonzero((B != prev).any(1))
            if len(changed):
                u, inv = np.unique(B[changed], axis=0, return_inverse=True)
                idx[changed] = (2 * u @ GT - bias).argmax(1)[inv.reshape(-1)]
            prev = B
            frames.append("\n".join("".join(r) for r in chars[idx.reshape(rows, cols)]))
            if len(frames) % 50 == 0:
                print(f"{i}/{total}", end="\r", file=sys.stderr)
        ok, frame = cap.read()
        i += 1
    with open(args.cache, "wb") as f:
        pickle.dump((frames, fps / args.step), f)
    return frames, fps / args.step


def play(frames, fps):
    out = sys.stdout
    out.write("\x1b[2J\x1b[?25l")
    t0 = time.perf_counter()
    try:
        for n, fr in enumerate(frames):
            target = t0 + n / fps
            now = time.perf_counter()
            if now > target + 1 / fps:
                continue
            out.write("\x1b[H" + fr)
            out.flush()
            time.sleep(max(0, target - time.perf_counter()))
    finally:
        out.write("\x1b[?25h\n")


def export(frames, fps):
    import shutil, subprocess
    s = args.scale
    fonts = []
    for path in args.font:
        fonts.append((ImageFont.truetype(path, 16 * s), set(TTFont(path, lazy=True).getBestCmap())))
    used = sorted(set("".join(frames)) - {"\n"})
    codes_sorted = np.array([ord(c) for c in used], dtype=np.uint32)
    atlas = np.zeros((len(used), 16 * s, 8 * s), dtype=np.uint8)
    for k, c in enumerate(used):
        f = next((ft for ft, cm in fonts if ord(c) in cm), fonts[0][0])
        img = Image.new("L", (8 * s, 16 * s), 0)
        ImageDraw.Draw(img).text((0, 0), c, fill=255, font=f)
        atlas[k] = np.asarray(img, dtype=np.uint8)

    lines0 = frames[0].split("\n")
    rows, cols = len(lines0), len(lines0[0])
    W, H = cols * 8 * s, rows * 16 * s
    W -= W % 2
    H -= H % 2
    tmp = args.export + ".tmp.mp4"
    vw = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*"mp4v"), fps, (cols * 8 * s, rows * 16 * s))
    for n, fr in enumerate(frames):
        codes = np.frombuffer(fr.replace("\n", "").encode("utf-32-le"), dtype="<u4")
        ids = np.searchsorted(codes_sorted, codes)
        grid = atlas[ids].reshape(rows, cols, 16 * s, 8 * s)
        img = grid.transpose(0, 2, 1, 3).reshape(rows * 16 * s, cols * 8 * s)
        vw.write(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))
        if n % 50 == 0:
            print(f"export {n}/{len(frames)}", end="\r", file=sys.stderr)
    vw.release()
    if shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-y", "-i", tmp, "-i", args.video, "-map", "0:v", "-map", "1:a?",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                        "-c:a", "aac", "-shortest", args.export], check=True)
        os.remove(tmp)
    else:
        os.replace(tmp, args.export)
        print("ffmpeg not found: exported without audio", file=sys.stderr)


if os.path.exists(args.cache):
    with open(args.cache, "rb") as f:
        frames, fps = pickle.load(f)
else:
    frames, fps = render_all()
if args.export:
    export(frames, fps)
else:
    play(frames, fps)