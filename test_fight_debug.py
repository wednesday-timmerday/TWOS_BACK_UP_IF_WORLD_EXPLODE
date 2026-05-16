#!/usr/bin/env python3
"""Debug test to see what's rendering and what isn't."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import pygame
    pygame.init()
    
    # Create a proper display
    screen = pygame.display.set_mode((1280, 720))
    pygame.display.set_caption("Fight Debug Test")
    
    from ui.fight.fight import Fight
    
    print("[DEBUG] Creating fight instance...")
    fight = Fight(None, screen)
    
    print("[DEBUG] Loading fight...")
    fight.load_fight("test_fight")
    
    print(f"[DEBUG] Fight state after load:")
    print(f"  - running: {fight.running}")
    print(f"  - module: {fight.module}")
    print(f"  - monster_image: {fight.monster_image is not None}")
    print(f"  - current_turn: {fight.current_turn}")
    print(f"  - bullet_engine active count: {fight.bullet_engine.active_count}")
    
    clock = pygame.time.Clock()
    
    for frame in range(300):  # 5 seconds at 60 FPS
        dt = clock.tick(60) / 1000.0
        
        # Update
        fight.update(dt)
        
        # Print debug info every 30 frames
        if frame % 30 == 0:
            print(f"[DEBUG] Frame {frame}:")
            print(f"  - current_turn: {fight.current_turn}")
            print(f"  - bullet_engine active count: {fight.bullet_engine.active_count}")
            if hasattr(fight, 'bullet_timer'):
                print(f"  - bullet_timer: {fight.bullet_timer:.2f}")
                print(f"  - bullet_interval: {fight.bullet_interval}")
        
        # Draw
        fight.draw()
        
        # Draw some debug info to screen
        font = pygame.font.Font(None, 24)
        debug_text = f"Frame: {frame} | Turn: {fight.current_turn} | Bullets: {fight.bullet_engine.active_count}"
        text_surf = font.render(debug_text, True, (255, 255, 255))
        screen.blit(text_surf, (10, 10))
        
        # Display
        pygame.display.flip()
        
        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                break
    
    print("[DEBUG] Test complete")
    pygame.quit()
    
except Exception as e:
    import traceback
    print(f"[ERROR] {e}")
    traceback.print_exc()
