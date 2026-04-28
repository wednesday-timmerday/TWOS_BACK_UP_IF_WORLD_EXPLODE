import math

SAMPLES = 256
AMPLITUDE = 120
OFFSET = 128

def heart_points(n=SAMPLES):
    pts = []
    for i in range(n):
        t = (i / n) * 2 * math.pi

        x = 16 * (math.sin(t) ** 3)
        y = (
            13 * math.cos(t)
            - 5 * math.cos(2 * t)
            - 2 * math.cos(3 * t)
            - math.cos(4 * t)
        )

        pts.append((x, y))
    return pts

def normalize(values):
    ys = [v[1] for v in values]
    min_y, max_y = min(ys), max(ys)

    return [
        int(OFFSET + AMPLITUDE * (y - min_y) / (max_y - min_y) * 2 - 1)
        for (_, y) in values
    ]

def make_frame():
    pts = heart_points()
    waveform = normalize(pts)
    return waveform

frame = make_frame()

print(frame[:20])