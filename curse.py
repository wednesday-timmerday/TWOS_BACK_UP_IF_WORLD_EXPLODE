import cv2
import pyvirtualcam

VIDEO_PATH = "Ego Renegade Boy ft. Kagamine Len.mp4"

cap = cv2.VideoCapture(VIDEO_PATH)

WIDTH = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
HEIGHT = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
FPS = cap.get(cv2.CAP_PROP_FPS)

if FPS <= 0:
    FPS = 30

with pyvirtualcam.Camera(width=WIDTH, height=HEIGHT, fps=FPS) as cam:
    print(f"virtual cam -> {cam.device}")

    while True:
        ret, frame = cap.read()

        # restart video when it ends
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        cam.send(rgb)
        cam.sleep_until_next_frame()

cap.release()