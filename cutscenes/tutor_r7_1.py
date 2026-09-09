import pygame

class cutscene:

    
    def __init__(self, player, world, loader):
        self.dialogue_id = "tutor_r7_1"
        self.player = player
        self.world = world
        self.loader = loader
        self.dt = 0
        self.screen_snapshot = None
    
        self.zoom_center_x = 0
        self.zoom_center_y = 0
        self.target_zoom_scale = 2.5
        self.current_zoom_scale = 1.0
        self.zoom_speed_per_sec = 6.0
        self.hold_duration = 1.5
        self.hold_timer = 0.0
        self.zoom = False
        self.zoom_state = "zooming"  # "zooming" -> "holding" -> "unzooming" -> "done"
        self.zoomed_snapshot = None
        self.draw_x = 0
        self.draw_y = 0
    
    def capture_screenshot(self):
        if self.screen_snapshot is None:
            self.screen_snapshot = self.player.screen.copy()
            return "YES"
    
    def _ease_toward(self, current, target):
        factor = 1 - pow(0.02, self.dt * self.zoom_speed_per_sec / 6.0)
        return current + (target - current) * factor
    
    def _rescale_snapshot(self):
        snapshot_width = self.screen_snapshot.get_width()
        snapshot_height = self.screen_snapshot.get_height()
        zoomed_width = int(snapshot_width * self.current_zoom_scale)
        zoomed_height = int(snapshot_height * self.current_zoom_scale)
    
        self.zoomed_snapshot = pygame.transform.scale(self.screen_snapshot, (zoomed_width, zoomed_height))
    
        self.draw_x = int(self.zoom_center_x - self.zoom_center_x * self.current_zoom_scale)
        self.draw_y = int(self.zoom_center_y - self.zoom_center_y * self.current_zoom_scale)
    
    def activate_zoom(self, dt=None):
        self.zoom = True
        if dt is not None:
            self.dt = dt
    
        if self.zoom_state == "zooming":
            self.current_zoom_scale = self._ease_toward(self.current_zoom_scale, self.target_zoom_scale)
            self._rescale_snapshot()
            if self.current_zoom_scale >= self.target_zoom_scale - 0.005:
                self.current_zoom_scale = self.target_zoom_scale
                self._rescale_snapshot()
                self.zoom_state = "holding"
                self.hold_timer = 0.0
    
        elif self.zoom_state == "holding":
            self.hold_timer += self.dt
            if self.hold_timer >= self.hold_duration:
                self.zoom_state = "unzooming"
    
        elif self.zoom_state == "unzooming":
            self.current_zoom_scale = self._ease_toward(self.current_zoom_scale, 1.0)
            self._rescale_snapshot()
            if self.current_zoom_scale <= 1.005:
                self.current_zoom_scale = 1.0
                self.zoom_state = "done"
                self.zoom = False
                return "YES"
    
    def draw_back(self, loader, screen):
        if self.screen_snapshot and self.zoomed_snapshot and self.zoom_state != "done":
            screen.blit(self.zoomed_snapshot, (self.draw_x, self.draw_y))
