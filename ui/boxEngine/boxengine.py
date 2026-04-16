import pygame
from assetsLoader import Loader


class BoxEngine:  # ! still mid name but whatever
    def __init__(self, world_loader):
        self.world_loader = world_loader
        self.part_loader = Loader("ui/boxEngine/parts")

        self.corner_left = pygame.image.load(
            self.part_loader.load("thingy_1.png")
        ).convert_alpha()
        self.corner_right = pygame.transform.flip(self.corner_left, True, False)

        self.filler = pygame.image.load(
            self.part_loader.load("thingy_2.png")
        ).convert_alpha()
        self.filler_under = pygame.image.load(
            self.part_loader.load("thingy_3.png")
        ).convert_alpha()

        self.refresh()

        self.dragging_btn = None
        self.drag_offset = (0, 0)

    def refresh(self):
        self.all_btns = []
        self.btn_rects = []
        self.btn_start_rects = []
        self.shadow_data = []

        # load btns
        for btn_id in range(3):
            path = self.part_loader.load(f"btn_{btn_id + 1}.png")
            img = pygame.image.load(path).convert_alpha()
            self.all_btns.append(img)

        # spawn pos (world space)
        for i, btn in enumerate(self.all_btns):
            rect = btn.get_rect(topleft=(80 * (i + 1), 10))
            self.btn_rects.append(rect)
            self.btn_start_rects.append(rect.copy())

        # trigger data (world space)
        for trigger in self.world_loader.triggers:
            self.shadow_data.append({
                "name": trigger["name"],
                "rect": pygame.Rect(trigger["x"], trigger["y"], trigger["w"], trigger["h"]),
                "curr_power": None,
                "snapped": False
            })
            print(self.shadow_data)

    def create_box(self, box_coords):
        x, y, w, h = box_coords

        self.corner_left_pos = (x, y + h)
        self.corner_right_pos = (x + w, y + h)

        self.filler_under_scaled = pygame.transform.scale(
            self.filler_under,
            (w - self.corner_left.get_width(), self.corner_left.get_height())
        )
        self.filler_under_pos = (x + self.corner_left.get_width(), y + h)

        self.filler_scaled = pygame.transform.scale(
            self.filler,
            (w + self.corner_left.get_width(), h)
        )
        self.filler_pos = (x, y)

    def handle_input(self):
        # mouse -> world space
        mouse_x = pygame.mouse.get_pos()[0] / 4
        mouse_y = pygame.mouse.get_pos()[1] / 4
        mouse_pos = (mouse_x, mouse_y)

        mouse_pressed = pygame.mouse.get_pressed()[0]

        # start drag
        if mouse_pressed and self.dragging_btn is None:
            for i, rect in enumerate(self.btn_rects):
                if rect.collidepoint(mouse_pos):
                    self.dragging_btn = i
                    self.drag_offset = (
                        mouse_pos[0] - rect.x,
                        mouse_pos[1] - rect.y
                    )
                    break

        # dragging (world space)
        if mouse_pressed and self.dragging_btn is not None:
            i = self.dragging_btn
            self.btn_rects[i].x = mouse_pos[0] - self.drag_offset[0]
            self.btn_rects[i].y = mouse_pos[1] - self.drag_offset[1]

        # release
        if not mouse_pressed and self.dragging_btn is not None:
            self.check_snap(self.dragging_btn)

            # go back to original pos
            self.btn_rects[self.dragging_btn] = self.btn_start_rects[self.dragging_btn].copy()

            self.dragging_btn = None

    def check_snap(self, btn_index):
        btn_rect = self.btn_rects[btn_index]

        for data in self.shadow_data:
            trect = data["rect"]
            print(data["name"])

            if btn_rect.colliderect(trect):
                if data["name"] == "shadow_platform":
                    if data["curr_power"] != btn_index:
                        data["curr_power"] = btn_index

                    data["snapped"] = True
            else:
                data["snapped"] = False

    def draw(self, screen, with_btns=False):
        # box (screen space)
        screen.blit(self.corner_left, (self.corner_left_pos[0], self.corner_left_pos[1]))
        screen.blit(self.corner_right, (self.corner_right_pos[0], self.corner_right_pos[1]))
        screen.blit(self.filler_under_scaled, (self.filler_under_pos[0], self.filler_under_pos[1]))
        screen.blit(self.filler_scaled, (self.filler_pos[0], self.filler_pos[1]))

        if not with_btns:
            return

        self.handle_input()

        # debug triggers
        # for data in self.shadow_data:
        #     pygame.draw.rect(
        #         screen,
        #         (255, 0, 0),
        #         pygame.Rect(
        #             data["rect"].x - self.world_loader.cam_x,
        #             data["rect"].y,
        #             data["rect"].w,
        #             data["rect"].h
        #         ),
        #         2
        #     )

        # draw assigned powers
        for data in self.shadow_data:
            if data["curr_power"] is not None:
                img = self.all_btns[data["curr_power"]]
                rect = img.get_rect(
                    center=(
                        data["rect"].centerx - self.world_loader.cam_x,
                        data["rect"].centery
                    )
                )
                screen.blit(img, rect)

        # draw btns
        for i, btn in enumerate(self.all_btns):
            screen.blit(
                btn,
                (
                    self.btn_rects[i].x,
                    self.btn_rects[i].y
                )
            )