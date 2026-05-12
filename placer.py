import json
import uuid

FILE_PATH = "worlds/level-spec.json"  # change this to your filename

# load file
with open(FILE_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

level = data["level_6"]

# starting settings
start_x = 200  # you can change this if you want
y = 180 - 8   # = 592
spacing = 8  # distance between spikes

# ensure enemies list exists
if "enemies" not in level:
    level["enemies"] = []

# add 75 chained spikes
for i in range(23):
    spike = {
        "type": "spike",
        "position": [
            start_x + i * spacing,
            y
        ],
        "id": str(uuid.uuid4())
    }
    level["enemies"].append(spike)

# save back
with open(FILE_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

print("DONE!! 75 spikes deployed in level_6. chain established. chaos achieved.")
