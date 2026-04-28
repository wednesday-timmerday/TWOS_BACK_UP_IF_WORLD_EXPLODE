import struct
import matplotlib.pyplot as plt
import time

def read_frames():
    frames = []
    with open("frames.dat", "rb") as f:
        while True:
            size = f.read(2)
            if not size:
                break
            (n,) = struct.unpack("H", size)
            data = list(f.read(n))
            frames.append(data)
    return frames

frames = read_frames()

plt.ion()
fig, ax = plt.subplots()

line, = ax.plot(frames[0])

ax.set_ylim(0, 255)

for frame in frames:
    line.set_ydata(frame)
    ax.draw_artist(ax.patch)
    ax.draw_artist(line)
    fig.canvas.flush_events()
    time.sleep(1/60)

plt.ioff()
plt.show()