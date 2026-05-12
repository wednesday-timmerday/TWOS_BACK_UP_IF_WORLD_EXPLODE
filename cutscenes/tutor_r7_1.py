import pygame

class cutscene:
    def __init__(self, player, world, loader):
        self.dialogue_id = "tutor_r7_1"
        self.player = player
        self.world = world
        self.loader = loader
        self.dt = 0
        self.screen_snapshot = None
        
        cam_x = getattr(world, "cam_x", 0)
        cam_y = getattr(world, "cam_y", 0)
        scale_factor = player.screen.get_width() / 320
        self.zoom_center_x = (player.world_x) * scale_factor
        self.zoom_center_y = (player.world_y) * scale_factor
        self.target_zoom_scale = 2.0
        self.current_zoom_scale = 1.0
        self.zoom_smooth_speed = 0.04  # Smoothing factor (0-1, lower = smoother)
    
    def capture_screenshot(self):
        """Capture the current screen as a snapshot (only once)"""
        if self.screen_snapshot is None:
            self.screen_snapshot = self.player.screen.copy()
    
    def draw_back(self, loader, screen):
        print(self.player.world_x)
        if self.screen_snapshot:
            # Smooth interpolation between current and target scale
            self.current_zoom_scale += (self.target_zoom_scale - self.current_zoom_scale) * self.zoom_smooth_speed
            
            # Get screen dimensions
            screen_width = screen.get_width()
            screen_height = screen.get_height()
            
            # Calculate zoomed size
            snapshot_width = self.screen_snapshot.get_width()
            snapshot_height = self.screen_snapshot.get_height()
            
            zoomed_width = int(snapshot_width * self.current_zoom_scale)
            zoomed_height = int(snapshot_height * self.current_zoom_scale)
            
            # Scale with nearest-neighbour to keep pixel art sharp
            zoomed_snapshot = pygame.transform.scale(self.screen_snapshot, (zoomed_width, zoomed_height))
            
            # Position the zoomed image so that zoom_center (screen coords) stays fixed
            # Formula: draw_pos = anchor_screen - anchor_screen * scale
            draw_x = int(self.zoom_center_x - self.zoom_center_x * self.current_zoom_scale)
            draw_y = int(self.zoom_center_y - self.zoom_center_y * self.current_zoom_scale)
            
            # Draw the zoomed snapshot
            screen.blit(zoomed_snapshot, (draw_x, draw_y))

