import keyboard
import obsws_python as obs

HOST = "localhost"
PORT = 4455
PASSWORD = "lzDpINHwsuF1H2l2"

SCENE_1 = "Scène 2"
SCENE_2 = "Scène 3"

client = obs.ReqClient(host=HOST, port=PORT, password=PASSWORD)

current = SCENE_1
pressed = set()

def on_press(event):
    global current

    if event.name in pressed:
        return

    pressed.add(event.name)

    current = SCENE_2 if current == SCENE_1 else SCENE_1
    client.set_current_program_scene(current)
    print(f"Switched to {current}")

def on_release(event):
    pressed.discard(event.name)

keyboard.on_press(on_press)
keyboard.on_release(on_release)

print("Press any key to toggle scenes.")
print("Press ESC to exit.")

keyboard.wait("esc")
client.disconnect()