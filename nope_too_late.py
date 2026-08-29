from pydub import AudioSegment
import os

INPUT_FOLDER = "music"
OUTPUT_FOLDER = "music_ogg"

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

for file in os.listdir(INPUT_FOLDER):
    if file.endswith(".mp3"):
        mp3_path = os.path.join(INPUT_FOLDER, file)
        ogg_path = os.path.join(OUTPUT_FOLDER, file.replace(".mp3", ".ogg"))

        print(f"Converting: {file}")

        audio = AudioSegment.from_mp3(mp3_path)
        audio.export(ogg_path, format="ogg")

print("Done.")
