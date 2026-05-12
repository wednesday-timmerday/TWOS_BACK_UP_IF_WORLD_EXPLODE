import tkinter as tk
import time
import re
import random
import numpy as np
import cv2
import mss
import easyocr
import pyautogui

# =========================
# REGION SELECTOR OVERLAY
# =========================

class RegionSelector:
    def __init__(self):
        self.root = tk.Tk()
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-alpha", 0.25)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="black")

        self.canvas = tk.Canvas(self.root, cursor="cross", bg="black")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.start_x = None
        self.start_y = None
        self.rect = None
        self.region = None

        self.canvas.bind("<Button-1>", self.start)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        self.root.mainloop()

    def start(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y,
            self.start_x, self.start_y,
            outline="red", width=2
        )

    def drag(self, event):
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def release(self, event):
        x1 = min(self.start_x, event.x)
        y1 = min(self.start_y, event.y)
        x2 = max(self.start_x, event.x)
        y2 = max(self.start_y, event.y)
        self.region = {"left": x1, "top": y1, "width": x2 - x1, "height": y2 - y1}
        print(">>> REGION LOCKED:", self.region)
        self.root.destroy()


# =========================
# OCR SETUP
# =========================

reader = easyocr.Reader(['en'], gpu=False)

last_typed = None
last_seen  = None
their_turn = True

DELAY_MIN = 0.7
DELAY_MAX = 2.5984727

total_couted = 1051


def capture(region):
    with mss.mss() as sct:
        img = np.array(sct.grab(region))
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)


def extract_numbers(text):
    return [int(n) for n in re.findall(r"\d+", text)]


# =========================
# MAIN FLOW
# =========================

print(">>> ENTERING SELECTION MODE... (drag box, ESC to cancel)")
selector = RegionSelector()
region = selector.region

if not region:
    print("NO REGION SELECTED. EXIT.")
    exit()

print(">>> SCANNING MODE ACTIVE ðŸ“¡")
print(">>> Waiting for them to send a number first...")

while True:
    img = capture(region)
    results = reader.readtext(img)
    text = " ".join([r[1] for r in results])
    numbers = extract_numbers(text)

    if numbers:
        highest = max(numbers)

        if highest != last_seen and highest != last_typed:
            print(f">>> THEY SENT: {highest}")
            last_seen = highest
            their_turn = True

        if their_turn and (last_typed is None or highest > last_typed):
            their_turn = False
            counter = highest + 1

            delay = random.uniform(DELAY_MIN, DELAY_MAX)
            print(f">>> WAITING {delay:.2f}s then typing: {counter}")
            time.sleep(delay)

            last_typed = counter
            for char in str(counter):
                pyautogui.typewrite(char)
                time.sleep(random.uniform(0.1, 0.36))
            pyautogui.sleep(0.1)
            pyautogui.press("enter")
            total_couted += 1
        else:
            print("BURRNNNNNN")

    time.sleep(0.4)
