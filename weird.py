import time
from yt_dlp import YoutubeDL

urls = [
    "https://www.youtube.com/watch?v=HTxwOxFt5d4",
    "https://www.youtube.com/watch?v=F38EuG2dAyM",
    "https://www.youtube.com/watch?v=JALbemLw3G4",
    "https://www.youtube.com/watch?v=YcO-MxPf_Vg",
    "https://www.youtube.com/watch?v=R401j1QAvEg",
    "https://www.youtube.com/watch?v=sqK-jh4TDXo",
    "https://www.youtube.com/watch?v=LLjfal8jCYI"
]

ydl_opts = {
    "format": "bestaudio/best",
    "outtmpl": "songs/%(id)s.%(ext)s",
    "quiet": True,
    "noplaylist": True,
}

with YoutubeDL(ydl_opts) as ydl:
    for url in urls:
        try:
            ydl.download([url])
        except Exception as e:
            print("FAILED:", url, e)

        time.sleep(5)  # ← THIS is your cooldown