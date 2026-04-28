import json
import math
import struct

FPS = 60
SAMPLES_PER_FRAME = 128
TOTAL_FRAMES = 300
WAVE_TYPE = "sine"

AMPLITUDE = 120
OFFSET = 128

def generate_wave(t):
    if WAVE_TYPE == "sine":
        return [
            int(OFFSET + AMPLITUDE * math.sin(2 * math.pi * (i / SAMPLES_PER_FRAME) + t * 0.1))
            for i in range(SAMPLES_PER_FRAME)
        ]
    elif WAVE_TYPE == "square":
        return [
            OFFSET + AMPLITUDE if (i + t) % 32 < 16 else OFFSET - AMPLITUDE
            for i in range(SAMPLES_PER_FRAME)
        ]

frames = []

for t in range(TOTAL_FRAMES):
    frames.append(generate_wave(t))

# SETTINGS
settings = {
    "fps": FPS,
    "samples_per_frame": SAMPLES_PER_FRAME,
    "total_frames": TOTAL_FRAMES,
    "wave_type": WAVE_TYPE
}

with open("settings.json", "w") as f:
    json.dump(settings, f)

# BINARY FILE
with open("frames.dat", "wb") as f:
    for frame in frames:
        f.write(struct.pack("H", len(frame)))
        f.write(bytearray(frame))

print("DONE BIG SHOT 💾")