
import json
import os
import shutil
import subprocess
import sys

import cv2
import numpy as np

SRC = sys.argv[1] if len(sys.argv) > 1 else "badapple.mp4"
OUT = os.path.join("worlds", "16")
FW, FH = 160, 92

os.makedirs(OUT, exist_ok=True)

cap = cv2.VideoCapture(SRC)
fps = cap.get(cv2.CAP_PROP_FPS) or 30
frames = []
ok, f = cap.read()
while ok:
    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, (FW, FH), interpolation=cv2.INTER_AREA)
    frames.append(np.packbits((g > 128).reshape(-1)))
    ok, f = cap.read()

np.save(os.path.join(OUT, "badapple.npy"), np.stack(frames))
with open(os.path.join(OUT, "badapple.json"), "w") as fh:
    json.dump({"fps": fps}, fh)

if shutil.which("ffmpeg"):
    subprocess.run(
        ["ffmpeg", "-y", "-i", SRC, "-vn", "-ac", "2", "-ar", "44100", os.path.join(OUT, "badapple.wav")],
        check=True,
    )
else:
    print("ffmpeg not found: no audio extracted")

print(f"{len(frames)} frames at {fps} fps")
