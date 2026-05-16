#!/usr/bin/env python3
"""Test to see if fight actually renders to the display."""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import pygame
    pygame.init()
    
    # Create a proper display
    screen = pygame.display.set_mode((1280, 720))
    pygame.display.set_caption("Fight Render Test")
    
    from ui.fight.fight import Fight
    
    print("[TEST] Creating fight instance...")
    fight = Fight(None, screen)  # renderer=None, true_screen=screen
    
    print("[TEST] Loading fight...")
    fight.load_fight("test_fight")
    
    print("[TEST] Starting render loop for 5 seconds...")
    clock = pygame.time.Clock()
    start_time = time.time()
    
    while time.time() - start_time < 5.0:
        dt = clock.tick(60) / 1000.0
        
        # Update
        fight.update(dt)
        
        # Draw
        fight.draw()
        
        # Display
        pygame.display.flip()
        
        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                break
    
    print("[TEST] Test complete - window should have shown for 5 seconds")
    pygame.quit()
    
except Exception as e:
    import traceback
    print(f"[ERROR] {e}")
    traceback.print_exc()
