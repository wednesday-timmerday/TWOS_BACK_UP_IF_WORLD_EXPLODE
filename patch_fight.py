
import sys

target = r"C:\Users\JorisDörenkämper\Desktop\python\SHAWOD\TWOS_BACK_UP_IF_WORLD_EXPLODE\ui\fight\fight.py"

with open(target, "rb") as f:
    data = f.read()

old = (
    b"    def draw_text(self, screen=None):\r\n"
    b"\r\n"
    b"            if screen is None:\r\n"
    b"                screen = self.screen\r\n"
    b"            \r\n"
    b"            # Only draw text during player's turn (not during enemy's turn)\r\n"
    b"            if self.current_turn == 1:\r\n"
    b"                return\r\n"
    b"                \r\n"
    b"            self.text_engine.draw(\r\n"
    b"\r\n"
    b"                x=180,\r\n"
    b"\r\n"
    b"                y=356,\r\n"
    b"\r\n"
    b"                text_color=(255, 255, 255),\r\n"
    b"\r\n"
    b"                choice_color=(180, 180, 180),\r\n"
    b"\r\n"
    b"                highlight_color=(255, 255, 0),\r\n"
    b"\r\n"
    b"                size=12,\r\n"
    b"\r\n"
    b"                surface=screen\r\n"
    b"\r\n"
    b"            )\r\n"
    b"\r\n"
    b"            if self.current_turn == 1:\r\n"
    b"\r\n"
    b"                # C++ renders offscreen, returns a Surface \xe2\x80\x93 blit it like anything else.\r\n"
    b"\r\n"
    b"                # Main loop's pygame.display.flip() handles the final present. No fighting.\r\n"
    b"\r\n"
    b"                pass\r\n"
    b"\r\n"
    b"            if self.current_turn == 1:\r\n"
    b"\r\n"
    b"                # C++ renders offscreen, returns a Surface \xc3\xa2\xe2\x82\xac\xe2\x80\x9d blit it like anything else.\r\n"
    b"\r\n"
    b"                # Main loop's pygame.display.flip() handles the final present. No fighting.\r\n"
    b"\r\n"
    b"                pass\r\n"
    b"\r\n"
)

new = (
    b"    def draw_text(self, screen=None):\r\n"
    b"\r\n"
    b"            if screen is None:\r\n"
    b"                screen = self.screen\r\n"
    b"\r\n"
    b"            in_bbox = getattr(self, 'text_in_bbox', 1)\r\n"
    b"\r\n"
    b"            if in_bbox:\r\n"
    b"                # IN_BBOX present: render normally during player's turn\r\n"
    b"                if self.current_turn == 1:\r\n"
    b"                    return\r\n"
    b"\r\n"
    b"                self.text_engine.draw(\r\n"
    b"                    x=180,\r\n"
    b"                    y=356,\r\n"
    b"                    text_color=(255, 255, 255),\r\n"
    b"                    choice_color=(180, 180, 180),\r\n"
    b"                    highlight_color=(255, 255, 0),\r\n"
    b"                    size=12,\r\n"
    b"                    surface=screen\r\n"
    b"                )\r\n"
    b"\r\n"
    b"            else:\r\n"
    b"                # IN_BBOX not present: render inside attack box during enemy's turn\r\n"
    b"                if self.current_turn == 0:\r\n"
    b"                    return\r\n"
    b"\r\n"
    b"                # Attack box is 360x360, centered at x=640, top at y=336\r\n"
    b"                # Place text near the bottom of the box\r\n"
    b"                self.text_engine.draw(\r\n"
    b"                    x=480,\r\n"
    b"                    y=650,\r\n"
    b"                    text_color=(255, 255, 255),\r\n"
    b"                    choice_color=(180, 180, 180),\r\n"
    b"                    highlight_color=(255, 255, 0),\r\n"
    b"                    size=12,\r\n"
    b"                    surface=screen\r\n"
    b"                )\r\n"
    b"\r\n"
)

if old not in data:
    print("ERROR: pattern not found - file may already be patched or differs from expected")
    sys.exit(1)

new_data = data.replace(old, new, 1)
with open(target, "wb") as f:
    f.write(new_data)
print("SUCCESS: fight.py patched")
