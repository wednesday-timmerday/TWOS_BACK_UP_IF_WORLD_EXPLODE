import os
import time
import sys
import shutil

time.sleep(1)  # wait for game to fully close

game_path = sys.argv[1]

try:
    if os.path.isdir(game_path):
        shutil.rmtree(game_path)
    else:
        os.remove(game_path)
    print("Deleted:", game_path)
except Exception as e:
    print("Failed to delete:", e)